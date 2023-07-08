import base64
import time
from io import BytesIO
from telethon import TelegramClient, events
from threading import Thread
from pymongo import MongoClient

# configs
from config import account, read_group_chats, read_private_messages, database_name

# telegram connect
api_id = account[0]
api_hash = account[1]
client = TelegramClient('my_account', api_id, api_hash)

# database connect
cluster = MongoClient("localhost:27017")
db = cluster[database_name]
collection_filters = db["filters"]
collection_words = db["words"]
collection_messages = db["messages"]

# global data
words = []
black_list = []


class GetBlackList(Thread):
    def __init__(self):
        Thread.__init__(self)
        print("GetBlackList is running")
        self.daemon = True
        self.start()

    def run(self):
        black_list_result = []

        try:
            results = collection_filters.find({})
            for result in results:
                val = result["chat_id"]
                black_list_result.append(val)

            global black_list
            black_list = black_list_result
            print("black list were taken: " + str(black_list_result))
        except Exception as e:
            print('ERROR [ GetBlackList ]: ', e)

        time.sleep(3600)
        self.run()


class GetKeyWords(Thread):
    def __init__(self):
        Thread.__init__(self)
        print("GetKeyWords is running")
        self.daemon = True
        self.start()

    def run(self):
        key_words_result = []

        try:
            results = collection_words.find({})
            for result in results:
                val = result["key_word"].lower()
                key_words_result.append(val)

            global words
            words = key_words_result
            print("keywords were taken: " + str(key_words_result))
        except Exception as e:
            print('ERROR [ GetKeyWords ]: ', e)

        time.sleep(3600)
        self.run()


def format_photo(image_buf):
    try:
        data = base64.b64encode(image_buf.getvalue()).decode()
        if not data: return None

        photo = 'data:image/jpeg;base64,' + data
        return photo
    except:
        return None


async def get_profile_photo(entity):
    try:
        image_buf = BytesIO()
        await client.download_profile_photo(entity, file=image_buf)

        return format_photo(image_buf)
    except:
        return None


async def get_message_photo(message):
    try:
        image_buf = BytesIO()
        await client.download_media(message, file=image_buf)

        return format_photo(image_buf)
    except:
        return None


def get_full_name(user_entity):
    try:
        first = user_entity.first_name

        if hasattr(user_entity, "last_name") and user_entity.last_name:
            last = user_entity.last_name
            return first + " " + last

        return first
    except:
        return None


async def db_write(message_data, id, type):
    try:
        message = message_data.message

        global_entity = await client.get_entity(id)
        user_entity = await client.get_entity(id if type == 'user' else message.from_id.user_id)

        data = {
            "chat_id": str(id),
            "title": None,
            "type": type,
            "image": await get_profile_photo(global_entity),
            "message_text": message.message,
            "files": [],
            "user": {
                'user_id': str(user_entity.id),
                'fullname': get_full_name(user_entity),
                'username': "@" + user_entity.username if hasattr(user_entity, "username") else None,
                'phone': user_entity.phone if hasattr(user_entity, "phone") else None,
                'image': await get_profile_photo(user_entity),
                'premium': user_entity.premium if hasattr(user_entity, "premium") else False
            },
            "date": message_data.date,
            "link": None,
        }

        if type == 'user':
            data['title'] = get_full_name(global_entity)

        if type == 'chat':
            data['title'] = global_entity.title if hasattr(global_entity, "title") else ""
            data['link'] = 'https://t.me/c/' + str(id) + '/' + str(message.id)

        message_photo = await get_message_photo(message)
        if message_photo:
            data['files'].append({
                'type': 'photo',
                'data': message_photo
            })

        collection_messages.insert_one(data)
        print(data["date"], '::', data["title"], '::', data['link'], '::', data["message_text"])
    except:
        return None


@client.on(events.NewMessage)
async def my_event_handler(event):
    try:
        peer_id = event.message.peer_id

        chat_id = None
        chat_type = None

        if hasattr(peer_id, "user_id"):
            chat_id = peer_id.user_id
            chat_type = "user"
            if not read_private_messages: return

        if hasattr(peer_id, "chat_id"):
            chat_id = peer_id.chat_id
            chat_type = "chat"
            if not read_group_chats: return

        if not chat_id or not chat_type: return

        if chat_id in black_list: return

        mes = event.message.message.lower()
        for word in words:
            if mes.find(word) != -1:
                await db_write(event, int(chat_id), chat_type)
                break
    except:
        return None


if __name__ == '__main__':
    GetKeyWords()
    GetBlackList()

    client.start()
    client.run_until_disconnected()
