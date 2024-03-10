import datetime
import logging
import math
from sqlalchemy import select, update, func
from db import session_maker

from models.user import User
from utils.CryptoAddressGenerator import CryptoAddressGenerator


class UserService:
    users_per_page = 20

    @staticmethod
    def is_exist(telegram_id: int) -> bool:
        with session_maker() as session:
            stmt = select(User).where(User.telegram_id == telegram_id)
            is_exist = session.execute(stmt)
            return is_exist.scalar() is not None

    @staticmethod
    def get_next_user_id() -> int:
        with session_maker() as session:
            query = select(User.id).order_by(User.id.desc()).limit(1)
            last_user_id = session.execute(query)
            last_user_id = last_user_id.scalar()
            if last_user_id is None:
                return 0
            else:
                return int(last_user_id) + 1

    @staticmethod
    def create(telegram_id: int, telegram_username: str):
        with session_maker() as session:
            next_user_id = UserService.get_next_user_id()
            crypto_addr_gen = CryptoAddressGenerator()
            crypto_addresses = crypto_addr_gen.get_addresses(i=0)
            new_user = User(
                id=next_user_id,
                telegram_username=telegram_username,
                telegram_id=telegram_id,
                btc_address=crypto_addresses['btc'],
                ltc_address=crypto_addresses['ltc'],
                trx_address=crypto_addresses['trx'],
                seed=crypto_addr_gen.mnemonic_str
            )
            session.add(new_user)
            session.commit()

    @staticmethod
    def update_username(telegram_id: int, telegram_username: str):
        with session_maker() as session:
            user_from_db = UserService.get_by_tgid(telegram_id)
            if user_from_db and user_from_db.telegram_username != telegram_username:
                stmt = update(User).where(User.telegram_id == telegram_id).values(telegram_username=telegram_username)
                session.execute(stmt)
                session.commit()

    @staticmethod
    def get_by_tgid(telegram_id: int) -> User:
        with session_maker() as session:
            stmt = select(User).where(User.telegram_id == telegram_id)
            user_from_db = session.execute(stmt)
            user_from_db = user_from_db.scalar()
            return user_from_db

    @staticmethod
    def can_refresh_balance(telegram_id: int) -> bool:
        with session_maker() as session:
            stmt = select(User.last_balance_refresh).where(User.telegram_id == telegram_id)
            user_last_refresh = session.execute(stmt)
            user_last_refresh = user_last_refresh.scalar()
            if user_last_refresh is None:
                return True
            now_time = datetime.datetime.now()
            timedelta = (now_time - user_last_refresh).total_seconds()
            return timedelta > 30

    @staticmethod
    def create_last_balance_refresh_data(telegram_id: int):
        time = datetime.datetime.now()
        with session_maker() as session:
            stmt = update(User).where(User.telegram_id == telegram_id).values(
                last_balance_refresh=time)
            session.execute(stmt)
            session.commit()

    @staticmethod
    def get_balances(telegram_id: int) -> dict:
        with session_maker() as session:
            stmt = select(User.btc_balance, User.ltc_balance, User.usdt_balance).where(User.telegram_id == telegram_id)
            user_balances = session.execute(stmt)
            user_balances = user_balances.fetchone()
            keys = ["btc_balance", "ltc_balance", "usdt_balance"]
            user_balances = dict(zip(keys, user_balances))
            return user_balances

    @staticmethod
    def get_addresses(telegram_id: int) -> dict:
        with session_maker() as session:
            stmt = select(User.btc_address, User.ltc_address, User.trx_address).where(User.telegram_id == telegram_id)
            user_addresses = session.execute(stmt)
            user_addresses = user_addresses.fetchone()
            keys = ["btc_address", "ltc_address", "trx_address"]
            user_addresses = dict(zip(keys, user_addresses))
            return user_addresses

    @staticmethod
    def update_crypto_balances(telegram_id: int, new_crypto_balances: dict):
        with session_maker() as session:
            stmt = update(User).where(User.telegram_id == telegram_id).values(
                btc_balance=new_crypto_balances["btc_balance"],
                ltc_balance=new_crypto_balances["ltc_balance"],
                usdt_balance=new_crypto_balances["usdt_balance"],
            )
            session.execute(stmt)
            session.commit()

    @staticmethod
    def update_top_up_amount(telegram_id, deposit_amount):
        with session_maker() as session:
            get_old_top_up_amount_stmt = select(User.top_up_amount).where(User.telegram_id == telegram_id)
            old_top_up_amount = session.execute(get_old_top_up_amount_stmt)
            old_top_up_amount = old_top_up_amount.scalar()
            stmt = update(User).where(User.telegram_id == telegram_id).values(
                top_up_amount=round(old_top_up_amount + deposit_amount, 2))
            session.execute(stmt)
            session.commit()

    @staticmethod
    def is_buy_possible(telegram_id, total_price):
        user = UserService.get_by_tgid(telegram_id)
        balance = user.top_up_amount - user.consume_records
        return balance >= total_price

    @staticmethod
    def update_consume_records(telegram_id: int, total_price: float):
        with session_maker() as session:
            get_old_consume_records_stmt = select(User.consume_records).where(User.telegram_id == telegram_id)
            old_consume_records = session.execute(get_old_consume_records_stmt)
            old_consume_records = old_consume_records.scalar()
            stmt = update(User).where(User.telegram_id == telegram_id).values(
                consume_records=old_consume_records + total_price)
            session.execute(stmt)
            session.commit()

    @staticmethod
    def get_users_tg_ids_for_sending():
        with session_maker() as session:
            stmt = select(User.telegram_id).where(User.can_receive_messages == True)
            user_ids = session.execute(stmt)
            user_ids = user_ids.scalars().all()
            return user_ids

    @staticmethod
    def reduce_consume_records(user_id: int, total_price):
        with session_maker() as session:
            old_consume_records_stmt = select(User.consume_records).where(User.id == user_id)
            old_consume_records = session.execute(old_consume_records_stmt)
            old_consume_records = old_consume_records.scalar()
            stmt = update(User).where(User.id == user_id).values(consume_records=old_consume_records - total_price)
            session.execute(stmt)
            session.commit()

    @staticmethod
    def get_new_users_by_timedelta(timedelta_int, page):
        with session_maker() as session:
            current_time = datetime.datetime.now()
            one_day_interval = datetime.timedelta(days=int(timedelta_int))
            time_to_subtract = current_time - one_day_interval
            stmt = select(User).where(User.registered_at >= time_to_subtract, User.telegram_username != None).limit(
                UserService.users_per_page).offset(
                page * UserService.users_per_page)
            count_stmt = select(func.count(User.id)).where(User.registered_at >= time_to_subtract)
            users = session.execute(stmt)
            users_count = session.execute(count_stmt)
            return users.scalars().all(), users_count.scalar_one()

    @staticmethod
    def get_max_page_for_users_by_timedelta(timedelta_int):
        with session_maker() as session:
            current_time = datetime.datetime.now()
            one_day_interval = datetime.timedelta(days=int(timedelta_int))
            time_to_subtract = current_time - one_day_interval
            stmt = select(func.count(User.id)).where(User.registered_at >= time_to_subtract,
                                                     User.telegram_username != None)
            users = session.execute(stmt)
            users = users.scalar_one()
            if users % UserService.users_per_page == 0:
                return users / UserService.users_per_page - 1
            else:
                return math.trunc(users / UserService.users_per_page)

    @staticmethod
    def get_all_users_count():
        with session_maker() as session:
            stmt = func.count(User.id)
            users_count = session.execute(stmt)
            return users_count.scalar()

    @staticmethod
    def update_receive_messages(telegram_id, new_value):
        with session_maker() as session:
            stmt = update(User).where(User.telegram_id == telegram_id).values(
                can_receive_messages=new_value)
            session.execute(stmt)
            session.commit()
