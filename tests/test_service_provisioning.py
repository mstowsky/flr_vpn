import pytest
from sqlalchemy import select

from app.models.provisioning_task import ProvisioningTask
from app.models.user import User
from app.services.provisioning import (
    complete_provisioning_task,
    create_provisioning_task,
    fail_provisioning_task,
    get_pending_provisioning_tasks,
    get_provisioning_task,
    get_user_provisioning_tasks,
    retry_provisioning_task,
)


@pytest.fixture
async def user(session):
    """Создаёт пользователя для тестов задач."""
    user = User(
        telegram_id=987654321,
        username="provisioning_test_user",
        first_name="Test",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_create_provisioning_task(session, user):
    task = await create_provisioning_task(
        session,
        user_id=user.id,
        task_type="create",
    )

    assert task.id is not None
    assert task.user_id == user.id
    assert task.task_type == "create"
    assert task.status == "pending"
    assert task.subscription_id is None
    assert task.completed_at is None


@pytest.mark.asyncio
async def test_create_provisioning_task_without_commit(session, user):
    task = await create_provisioning_task(
        session,
        user_id=user.id,
        task_type="extend",
        commit=False,
    )

    assert task.id is not None
    assert task.status == "pending"

    stored_task = await get_provisioning_task(session, task.id)
    assert stored_task is not None
    assert stored_task.task_type == "extend"


@pytest.mark.asyncio
async def test_create_provisioning_task_rejects_invalid_type(
    session,
    user,
):
    with pytest.raises(ValueError, match="Недопустимый тип задачи"):
        await create_provisioning_task(
            session,
            user_id=user.id,
            task_type="invalid",
        )


@pytest.mark.asyncio
async def test_get_provisioning_task_returns_none_for_missing_id(session):
    task = await get_provisioning_task(session, 999999)

    assert task is None


@pytest.mark.asyncio
async def test_get_pending_provisioning_tasks(session, user):
    first = await create_provisioning_task(
        session,
        user_id=user.id,
        task_type="create",
    )
    second = await create_provisioning_task(
        session,
        user_id=user.id,
        task_type="extend",
    )

    await complete_provisioning_task(
        session,
        task_id=first.id,
        result_message="Доступ настроен",
    )

    pending = await get_pending_provisioning_tasks(session)

    assert [task.id for task in pending] == [second.id]


@pytest.mark.asyncio
async def test_get_user_provisioning_tasks(session, user):
    first = await create_provisioning_task(
        session,
        user_id=user.id,
        task_type="create",
    )
    second = await create_provisioning_task(
        session,
        user_id=user.id,
        task_type="extend",
    )

    other_user = User(
        telegram_id=987654322,
        username="another_provisioning_user",
    )
    session.add(other_user)
    await session.commit()
    await session.refresh(other_user)

    other_task = await create_provisioning_task(
        session,
        user_id=other_user.id,
        task_type="create",
    )

    tasks = await get_user_provisioning_tasks(
        session,
        user_id=user.id,
    )

    assert len(tasks) == 2
    assert {task.id for task in tasks} == {first.id, second.id}
    assert all(task.user_id == user.id for task in tasks)
    assert other_task.id not in {task.id for task in tasks}


@pytest.mark.asyncio
async def test_complete_provisioning_task(session, user):
    task = await create_provisioning_task(
        session,
        user_id=user.id,
        task_type="create",
    )

    completed = await complete_provisioning_task(
        session,
        task_id=task.id,
        result_message="Клиент создан в H UI",
    )

    assert completed.status == "completed"
    assert completed.result_message == "Клиент создан в H UI"
    assert completed.completed_at is not None
    assert completed.updated_at is not None


@pytest.mark.asyncio
async def test_complete_missing_task_raises_error(session):
    with pytest.raises(ValueError, match="не найдена"):
        await complete_provisioning_task(
            session,
            task_id=999999,
        )


@pytest.mark.asyncio
async def test_completed_task_cannot_be_completed_again(session, user):
    task = await create_provisioning_task(
        session,
        user_id=user.id,
        task_type="create",
    )

    await complete_provisioning_task(
        session,
        task_id=task.id,
    )

    with pytest.raises(ValueError, match="уже выполнена"):
        await complete_provisioning_task(
            session,
            task_id=task.id,
        )


@pytest.mark.asyncio
async def test_fail_provisioning_task(session, user):
    task = await create_provisioning_task(
        session,
        user_id=user.id,
        task_type="extend",
    )

    failed = await fail_provisioning_task(
        session,
        task_id=task.id,
        result_message="Не удалось найти клиента в H UI",
    )

    assert failed.status == "failed"
    assert failed.result_message == "Не удалось найти клиента в H UI"
    assert failed.completed_at is None


@pytest.mark.asyncio
async def test_completed_task_cannot_be_failed(session, user):
    task = await create_provisioning_task(
        session,
        user_id=user.id,
        task_type="create",
    )

    await complete_provisioning_task(
        session,
        task_id=task.id,
    )

    with pytest.raises(ValueError, match="Нельзя пометить"):
        await fail_provisioning_task(
            session,
            task_id=task.id,
            result_message="Ошибка",
        )


@pytest.mark.asyncio
async def test_retry_failed_task_does_not_create_duplicate(
    session,
    user,
):
    task = await create_provisioning_task(
        session,
        user_id=user.id,
        task_type="create",
    )
    task_id = task.id

    await fail_provisioning_task(
        session,
        task_id=task_id,
        result_message="Временная ошибка",
    )

    retried = await retry_provisioning_task(
        session,
        task_id=task_id,
    )

    assert retried.id == task_id
    assert retried.status == "pending"
    assert retried.result_message is None
    assert retried.completed_at is None

    result = await session.execute(
        select(ProvisioningTask).where(
            ProvisioningTask.user_id == user.id
        )
    )
    all_tasks = list(result.scalars().all())

    assert len(all_tasks) == 1


@pytest.mark.asyncio
async def test_retry_pending_task_raises_error(session, user):
    task = await create_provisioning_task(
        session,
        user_id=user.id,
        task_type="create",
    )

    with pytest.raises(ValueError, match="Повторить можно только"):
        await retry_provisioning_task(
            session,
            task_id=task.id,
        )


@pytest.mark.asyncio
async def test_fail_missing_task_raises_error(session):
    with pytest.raises(ValueError, match="не найдена"):
        await fail_provisioning_task(
            session,
            task_id=999999,
            result_message="Ошибка",
        )


@pytest.mark.asyncio
async def test_retry_missing_task_raises_error(session):
    with pytest.raises(ValueError, match="не найдена"):
        await retry_provisioning_task(
            session,
            task_id=999999,
        )