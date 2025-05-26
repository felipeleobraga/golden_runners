import os

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret")
SQLALCHEMY_DATABASE_URI = "postgresql://postgres:SZhQlNwPuOLskuBbJKGWriPwtqqfuDVq@shortline.proxy.rlwy.net:29880/railway"
SQLALCHEMY_TRACK_MODIFICATIONS = False