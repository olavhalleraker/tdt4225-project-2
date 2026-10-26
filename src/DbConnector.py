import os
from urllib.parse import quote_plus

from pymongo import MongoClient


class DbConnector:
    """
    Connects to the MongoDB server. We run MongoDB 7.0.1 locally in Docker
    (see README.md), but the same class works against the IDI virtual machine.

    The connection settings are read from environment variables.

    DB_HOST     - server address            (default "localhost")
    DB_PORT     - server port               (default 27017)
    DB_NAME     - database name             (default "movies_db")
    DB_USER     - MongoDB user              (default "tdt4225")
    DB_PASSWORD - password for DB_USER      (required, no default)
    """

    def __init__(self,
                 DATABASE=os.getenv("DB_NAME", "movies_db"),
                 HOST=os.getenv("DB_HOST", "localhost"),
                 PORT=int(os.getenv("DB_PORT", "27017")),
                 USER=os.getenv("DB_USER", "tdt4225"),
                 PASSWORD=os.getenv("DB_PASSWORD")):
        if PASSWORD is None:
            raise RuntimeError("Set the DB_PASSWORD environment variable before connecting.")
        uri = "mongodb://%s:%s@%s:%d/%s" % (quote_plus(USER), quote_plus(PASSWORD), HOST, PORT, DATABASE)

        # Connect to the database. server_info() makes a round trip, so a wrong
        # host or password fails here and not in the first query.
        try:
            self.client = MongoClient(uri)
            self.db = self.client[DATABASE]
            self.server_version = self.client.server_info()["version"]
        except Exception as e:
            print("ERROR: Failed to connect to db:", e)
            raise

        print("Connected to MongoDB", self.server_version)
        # get database information
        print("You are connected to the database:", self.db.name)
        print("-----------------------------------------------\n")

    def close_connection(self):
        # close the DB connection
        self.client.close()
        print("\n-----------------------------------------------")
        print("Connection to %s-db is closed" % self.db.name)
