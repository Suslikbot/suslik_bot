class MockBot:
    def __init__(self):
        self.sent = []

    async def __call__(self, method, *_args, **_kwargs):
        # aiogram вызывает bot(method)
        self.sent.append(method)

    async def send_message(self, *args, **kwargs):
        self.sent.append(("send_message", args, kwargs))

    async def send_photo(self, *args, **kwargs):
        self.sent.append(("send_photo", args, kwargs))
