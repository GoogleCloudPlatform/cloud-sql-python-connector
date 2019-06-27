import asyncio
import random
import time
from threading import Thread

class Dice:
    def __init__(self):
        self._number = int(random.random() * 6)
        print(self._number)

    def num(self):
        return self._number

    async def roll(self):
        self._number = int(random.random() * 6)

    async def new_num(self):
        while True:
          print("Roll")
          await self.roll()
          await asyncio.sleep(1)

async def do_some_work(x):
    print("Waiting " + str(x))
    await asyncio.sleep(x)
    print("Back!")

loop = asyncio.new_event_loop()

def func(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

x = Thread(target=func, args=(loop,))
x.start()

asyncio.run_coroutine_threadsafe(do_some_work(5), loop)

loop2 = asyncio.new_event_loop()
loop2.call_soon(do_some_work, 1)
loop2.run_until_complete()
