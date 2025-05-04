import os

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'you-should-change-this')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///weguide.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
