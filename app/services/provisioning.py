from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan
from app.models.provisioning_task import ProvisioningTask
from app.models.subscription import Subscription
from app.services.subscriptions import create_subscription

VALID_TASK_TYPES = {"create", "extend", "disable"}
VALID_TASK_STATUSES = {"pending", "completed", "failed"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def create_provisioning_task(
    session: AsyncSession,
    *,
    user_id: int,
    task_type: str,
    subscription_id: int | None = None,
    commit: bool = True,
) -> ProvisioningTask:
    """Создаёт задачу ручной настройки VPN-доступа."""
    if task_type not in VALID_TASK_TYPES:
        raise ValueError(f"Недопустимый тип задачи: {task_type}")

    task = ProvisioningTask(
        user_id=user_id,
        subscription_id=subscription_id,
        task_type=task_type,
        status="pending",
    )
    session.add(task)

    if commit:
        await session.commit()
        await session.refresh(task)
    else:
        await session.flush()

    return task


async def get_provisioning_task(
    session: AsyncSession,
    task_id: int,
) -> ProvisioningTask | None:
    """Возвращает задачу по ID."""
    result = await session.execute(
        select(ProvisioningTask).where(ProvisioningTask.id == task_id)
    )
    return result.scalar_one_or_none()


async def get_pending_provisioning_tasks(
    session: AsyncSession,
) -> list[ProvisioningTask]:
    """Возвращает ожидающие выполнения задачи от старых к новым."""
    result = await session.execute(
        select(ProvisioningTask)
        .where(ProvisioningTask.status == "pending")
        .order_by(ProvisioningTask.created_at, ProvisioningTask.id)
    )
    return list(result.scalars().all())


async def get_user_provisioning_tasks(
    session: AsyncSession,
    *,
    user_id: int,
) -> list[ProvisioningTask]:
    """Возвращает задачи пользователя от новых к старым."""
    result = await session.execute(
        select(ProvisioningTask)
        .where(ProvisioningTask.user_id == user_id)
        .order_by(
            ProvisioningTask.created_at.desc(),
            ProvisioningTask.id.desc(),
        )
    )
    return list(result.scalars().all())


async def complete_provisioning_task(
    session: AsyncSession,
    *,
    task_id: int,
    result_message: str | None = None,
    commit: bool = True,
) -> ProvisioningTask:
    """Отмечает задачу выполненной."""

    task = await get_provisioning_task(session, task_id)

    if task is None:
        raise ValueError(f"Задача с ID {task_id} не найдена")

    if task.status == "completed":
        raise ValueError(f"Задача с ID {task_id} уже выполнена")

    current_time = _utc_now()

    if task.task_type == "disable":
        if task.subscription_id is None:
            raise ValueError(
                f"У задачи отключения ID {task_id} "
                "не указана подписка."
            )

        subscription = await session.get(
            Subscription,
            task.subscription_id,
        )

        if subscription is None:
            raise ValueError(
                f"Подписка ID {task.subscription_id} не найдена."
            )

        subscription.status = "cancelled"
        subscription.updated_at = current_time

    task.status = "completed"
    task.result_message = result_message
    task.completed_at = current_time
    task.updated_at = current_time


    if commit:
        await session.commit()
        await session.refresh(task)
    else:
        await session.flush()

    return task


async def fail_provisioning_task(
    session: AsyncSession,
    *,
    task_id: int,
    result_message: str,
    commit: bool = True,
) -> ProvisioningTask:
    """Отмечает задачу неудачной, сохраняя причину ошибки."""
    task = await get_provisioning_task(session, task_id)

    if task is None:
        raise ValueError(f"Задача с ID {task_id} не найдена")

    if task.status == "completed":
        raise ValueError(
            f"Нельзя пометить выполненную задачу {task_id} как неудачную"
        )

    task.status = "failed"
    task.result_message = result_message
    task.completed_at = None
    task.updated_at = _utc_now()

    if commit:
        await session.commit()
        await session.refresh(task)
    else:
        await session.flush()

    return task


async def retry_provisioning_task(
    session: AsyncSession,
    *,
    task_id: int,
    commit: bool = True,
) -> ProvisioningTask:
    """Возвращает неудачную задачу в очередь без создания дубликата."""
    task = await get_provisioning_task(session, task_id)

    if task is None:
        raise ValueError(f"Задача с ID {task_id} не найдена")

    if task.status != "failed":
        raise ValueError(
            f"Повторить можно только неудачную задачу; "
            f"текущий статус: {task.status}"
        )

    task.status = "pending"
    task.result_message = None
    task.completed_at = None
    task.updated_at = _utc_now()

    if commit:
        await session.commit()
        await session.refresh(task)
    else:
        await session.flush()

    return task


@pytest.mark.asyncio
async def test_complete_disable_task_cancels_subscription(
    session,
    user,
):
    """При выполнении задачи disable подписка получает статус cancelled."""

    plan = Plan(
        name="Тестовый тариф",
        price_rub=199,
        duration_days=30,
        max_devices=3,
        is_active=True,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)

    subscription = await create_subscription(
        session,
        user_id=user.id,
        plan_id=plan.id,
    )

    task = await create_provisioning_task(
        session,
        user_id=user.id,
        task_type="disable",
        subscription_id=subscription.id,
    )

    completed = await complete_provisioning_task(
        session,
        task_id=task.id,
        result_message="Клиент отключён в H UI",
    )

    await session.refresh(subscription)

    assert completed.status == "completed"
    assert completed.result_message == "Клиент отключён в H UI"
    assert completed.completed_at is not None

    assert subscription.status == "cancelled"
    assert subscription.updated_at is not None


@pytest.mark.asyncio
async def test_complete_disable_task_rejects_missing_subscription_id(
    session,
    user,
):
    """Задачу disable без ID подписки нельзя завершить."""

    task = await create_provisioning_task(
        session,
        user_id=user.id,
        task_type="disable",
    )

    with pytest.raises(ValueError, match="не указана подписка"):
        await complete_provisioning_task(
            session,
            task_id=task.id,
        )

    await session.refresh(task)

    assert task.status == "pending"
    assert task.completed_at is None