"""重试装饰器"""
import time
import asyncio
import logging
from functools import wraps
from typing import Callable, Type, Tuple

logger = logging.getLogger(__name__)


class MaxRetriesExceededError(Exception):
    """超过最大重试次数"""
    pass


def retry_on_failure(
    max_retries: int = 3,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    delay: float = 2.0,
    exponential_backoff: bool = True
) -> Callable:
    """重试装饰器

    Args:
        max_retries: 最大重试次数
        exceptions: 需要重试的异常类型
        delay: 重试延迟(秒)
        exponential_backoff: 是否使用指数退避
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            retry_count = 0
            current_delay = delay

            while retry_count <= max_retries:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    retry_count += 1

                    if retry_count > max_retries:
                        logger.error(
                            f"{func.__name__} 失败,已达最大重试次数({max_retries}): {e}"
                        )
                        raise MaxRetriesExceededError(
                            f"超过最大重试次数({max_retries}), 最后错误: {e}"
                        )

                    logger.warning(
                        f"{func.__name__} 失败,第{retry_count}次重试 (剩余{max_retries - retry_count}次): {e}"
                    )

                    time.sleep(current_delay)

                    if exponential_backoff:
                        current_delay *= 2

        return wrapper
    return decorator


def async_retry_on_failure(
    max_retries: int = 3,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    delay: float = 2.0,
    exponential_backoff: bool = True
) -> Callable:
    """异步重试装饰器

    Args:
        max_retries: 最大重试次数
        exceptions: 需要重试的异常类型
        delay: 重试延迟(秒)
        exponential_backoff: 是否使用指数退避
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            retry_count = 0
            current_delay = delay

            while retry_count <= max_retries:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    retry_count += 1

                    if retry_count > max_retries:
                        logger.error(
                            f"{func.__name__} 失败,已达最大重试次数({max_retries}): {e}"
                        )
                        raise MaxRetriesExceededError(
                            f"超过最大重试次数({max_retries}), 最后错误: {e}"
                        )

                    logger.warning(
                        f"{func.__name__} 失败,第{retry_count}次重试 (剩余{max_retries - retry_count}次): {e}"
                    )

                    await asyncio.sleep(current_delay)

                    if exponential_backoff:
                        current_delay *= 2

        return wrapper
    return decorator


def retry_with_exceptions(
    func: Callable,
    max_retries: int = 3,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    delay: float = 2.0,
    exponential_backoff: bool = True
):
    """函数式重试（非装饰器，用于内部调用）

    Args:
        func: 要执行的函数（无参数的callable）
        max_retries: 最大重试次数
        exceptions: 需要重试的异常类型
        delay: 重试延迟(秒)
        exponential_backoff: 是否使用指数退避

    Returns:
        函数执行结果
    """
    retry_count = 0
    current_delay = delay

    while retry_count <= max_retries:
        try:
            return func()
        except exceptions as e:
            retry_count += 1

            if retry_count > max_retries:
                logger.error(
                    f"重试失败,已达最大重试次数({max_retries}): {e}"
                )
                raise

            logger.warning(
                f"执行失败,第{retry_count}次重试 (剩余{max_retries - retry_count}次): {e}"
            )

            time.sleep(current_delay)

            if exponential_backoff:
                current_delay *= 2
