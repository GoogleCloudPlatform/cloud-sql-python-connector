import socket
import ssl
from typing import Any, TYPE_CHECKING

SERVER_PROXY_PORT = 3307

if TYPE_CHECKING:
    import aiomysql

async def connect(
    ip_address: str, ctx: ssl.SSLContext, **kwargs: Any
    ) -> "aiomysql.connections.Connection":
        """Helper function to create a aiomysql DB-API connection object.

        :type ip_address: str
        :param ip_address: A string containing an IP address for the Cloud SQL
            instance.

        :type ctx: ssl.SSLContext
        :param ctx: An SSLContext object created from the Cloud SQL server CA
            cert and ephemeral cert.

        :rtype: aiomysql.Connection
        :returns: A aiomysql Connection object for the Cloud SQL instance.
        """
        try:
            import aiomysql
        except ImportError:
            raise ImportError(
                'Unable to import module "aiomysql." Please install and try again.'
            )

        # Create pymysql connection object and hand in pre-made connection
        user = kwargs.pop("user")
        db = kwargs.pop("db")
        passwd = kwargs.pop("password")
        conn = await aiomysql.connect(user=user, password=passwd, db=db, host=ip_address, port=SERVER_PROXY_PORT, ssl=ctx, **kwargs)
        return conn
