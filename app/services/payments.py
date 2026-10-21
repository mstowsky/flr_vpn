from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment
from app.models.plan import Plan


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
    """Подтверждает оплату и активирует или продлевает подписку.

    Изменение статуса платежа и изменение подписки фиксируются
    одной транзакцией.

    Возвращает:
        Payment — если платёж успешно обработан или уже обработан.
        None — если платёж с указанным ID не найден.

    Raises:
        ValueError — если платёж имеет недопустимый статус.
    """
    from app.services.subscriptions import extend_subscription

    payment = await get_payment_by_id(session, payment_id)

    if payment is None:
        return None

    # Повторная обработка не должна продлевать подписку ещё раз.
    if payment.status == "succeeded":
        return payment

    # Обрабатывать как успешные можно только ожидающие платежи.
    if payment.status != "pending":
        raise ValueError(
            f"Нельзя подтвердить платёж со статусом "
            f"'{payment.status}'."
        )

    try:
        # Создаём или продлеваем подписку без отдельного commit.
        await extend_subscription(
            session,
            user_id=payment.user_id,
            plan_id=payment.plan_id,
            commit=False,
        )

        # Помечаем платёж успешным в той же транзакции.
        payment.status = "succeeded"

        await session.commit()
        await session.refresh(payment)

    except Exception:
        await session.rollback()
        raise

    return payment