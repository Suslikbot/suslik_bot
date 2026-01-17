class MockBot:
    def __init__(self):
        self.sent = []

    async def __call__(self, method, *args, **kwargs):
        # aiogram вызывает bot(method)
        self.sent.append(method)
        return None

    async def send_message(self, *args, **kwargs):
        self.sent.append(("send_message", args, kwargs))
        return None

    async def send_photo(self, *args, **kwargs):
        self.sent.append(("send_photo", args, kwargs))
        return None
