from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.plan import Plan
from app.models.user import User


async def create_payment(
    session: AsyncSession,
    *,
    user_id: int,
    plan_id: int,
) -> Payment:
    """Создаёт заказ на оплату активного тарифа."""

    result = await session.execute(
        select(Plan).where(
            Plan.id == plan_id,
            Plan.is_active.is_(True),
        )
    )
    plan = result.scalar_one_or_none()

    if plan is None:
        raise ValueError(
            f"Активный тариф с ID {plan_id} не найден."
        )

    payment = Payment(
        user_id=user_id,
        plan_id=plan.id,
        amount_rub=plan.price_rub,
        currency="RUB",
        status="pending",
        provider="fake",
    )

    session.add(payment)
    await session.commit()
    await session.refresh(payment)

    return payment


async def get_payment_by_id(
    session: AsyncSession,
    payment_id: int,
) -> Payment | None:
    """Возвращает заказ по ID или None, если он не найден."""

    result = await session.execute(
        select(Payment).where(Payment.id == payment_id)
    )
    return result.scalar_one_or_none()


async def get_user_payments(
    session: AsyncSession,
    user_id: int,
) -> list[Payment]:
    """Возвращает историю заказов пользователя от новых к старым."""

    result = await session.execute(
        select(Payment)
        .where(Payment.user_id == user_id)
        .order_by(Payment.created_at.desc(), Payment.id.desc())
    )
    return list(result.scalars().all())


async def update_payment_status(
    session: AsyncSession,
    payment_id: int,
    new_status: str,
) -> Payment | None:
    """Изменяет статус платежа с проверкой допустимости перехода.

    Возвращает обновлённый Payment или None, если платёж не найден.
    Повторная установка текущего статуса не вызывает изменений.
    """
    allowed_statuses = {"pending", "succeeded", "cancelled", "failed"}
    terminal_statuses = {"succeeded", "cancelled", "failed"}

    if new_status not in allowed_statuses:
        raise ValueError(
            f"Недопустимый статус платежа: {new_status}."
        )

    payment = await get_payment_by_id(session, payment_id)

    if payment is None:
        return None

    # Повторный запрос с тем же статусом безопасен.
    if payment.status == new_status:
        return payment

    # Изменять можно только ещё не завершённые платежи.
    if payment.status != "pending":
        raise ValueError(
            f"Нельзя изменить статус платежа с "
            f"'{payment.status}' на '{new_status}'."
        )

    # Нельзя вернуть платёж из pending в pending через изменение
    # статуса — этот случай уже обработан выше.
    if new_status not in terminal_statuses:
        raise ValueError(
            f"Недопустимый переход статуса: "
            f"'{payment.status}' -> '{new_status}'."
        )

    payment.status = new_status

    await session.commit()
    await session.refresh(payment)

    return payment


async def process_successful_payment(
    session: AsyncSession,
    payment_id: int,
) -> Payment | None:
    """Подтверждает оплату, изменяет подписку и создаёт задачу VPN.

    Все изменения выполняются в одной транзакции.
    Повторная обработка успешного платежа безопасна.
    """
    from app.services.provisioning import create_provisioning_task
    from app.services.subscriptions import (
        extend_subscription,
        get_user_subscription,
    )

    payment = await get_payment_by_id(session, payment_id)

    if payment is None:
        return None

    # Повторная обработка не должна создавать новую задачу.
    if payment.status == "succeeded":
        return payment

    if payment.status != "pending":
        raise ValueError(
            f"Нельзя подтвердить платёж со статусом "
            f"'{payment.status}'."
        )

    try:
        # Проверяем подписку ДО продления, чтобы правильно
        # определить тип задачи.
        current_subscription = await get_user_subscription(
            session,
            payment.user_id,
        )

        task_type = (
            "extend"
            if current_subscription is not None
            else "create"
        )

        # Продлеваем подписку или создаём новую без commit.
        subscription = await extend_subscription(
            session,
            user_id=payment.user_id,
            plan_id=payment.plan_id,
            commit=False,
        )

        # Для новой подписки нужен ID перед созданием задачи.
        await session.flush()

        # Создаём задачу в той же транзакции.
        await create_provisioning_task(
            session,
            user_id=payment.user_id,
            task_type=task_type,
            subscription_id=subscription.id,
            commit=False,
        )

        # Успешная платная подписка лишает пользователя права на пробный период.
        if payment.amount_rub > 0:
            user = await session.get(User, payment.user_id)
            if user is not None:
                user.has_used_trial = True

        # Платёж, подписка, задача и флаг фиксируются вместе.
        payment.status = "succeeded"

        await session.commit()
        await session.refresh(payment)

    except Exception:
        await session.rollback()
        raise

    return payment