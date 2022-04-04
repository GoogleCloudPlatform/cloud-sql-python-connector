import ssl
from typing import Any, TYPE_CHECKING

SERVER_PROXY_PORT = 3307

if TYPE_CHECKING:
    import asyncpg

async def connect(
    ip_address: str, ctx: ssl.SSLContext, **kwargs: Any
    ) -> "asyncpg.Connection":
        """Helper function to create an asyncpg DB-API connection object.

        :type ip_address: str
        :param ip_address: A string containing an IP address for the Cloud SQL
            instance.

        :type ctx: ssl.SSLContext
        :param ctx: An SSLContext object created from the Cloud SQL server CA
            cert and ephemeral cert.

        :rtype: asyncpg.Connection
        :returns: An asyncpg Connection object for the Cloud SQL instance.
        """
        try:
            import asyncpg
        except ImportError:
            raise ImportError(
                'Unable to import module "asyncpg." Please install and try again.'
            )
        user = kwargs.pop("user")
        db = kwargs.pop("db")
        passwd = kwargs.pop("password", None)
        return await asyncpg.connect(
            user=user,
            database=db,
            password=passwd,
            host=ip_address,
            port=SERVER_PROXY_PORT,
            ssl=ctx,
            **kwargs,
        )
