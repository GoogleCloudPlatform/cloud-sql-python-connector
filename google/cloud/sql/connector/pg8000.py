import ssl
from typing import Any, TYPE_CHECKING

SERVER_PROXY_PORT = 3307

if TYPE_CHECKING:
    import pg8000


def connect(
    ip_address: str, ctx: ssl.SSLContext, **kwargs: Any
) -> "pg8000.dbapi.Connection":
    """Helper function to create a pg8000 DB-API connection object.

    :type ip_address: str
    :param ip_address: A string containing an IP address for the Cloud SQL
        instance.

    :type ctx: ssl.SSLContext
    :param ctx: An SSLContext object created from the Cloud SQL server CA
        cert and ephemeral cert.


    :rtype: pg8000.dbapi.Connection
    :returns: A pg8000 Connection object for the Cloud SQL instance.
    """
    try:
        import pg8000
    except ImportError:
        raise ImportError(
            'Unable to import module "pg8000." Please install and try again.'
        )
    user = kwargs.pop("user")
    db = kwargs.pop("db")
    passwd = kwargs.pop("password", None)
    setattr(ctx, "request_ssl", False)
    return pg8000.dbapi.connect(
        user,
        database=db,
        password=passwd,
        host=ip_address,
        port=SERVER_PROXY_PORT,
        ssl_context=ctx,
        **kwargs,
    )
