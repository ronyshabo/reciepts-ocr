class Receipt:
    def __init__(self, id, vendor, date, total, items):
        self.id = id
        self.vendor = vendor
        self.date = date
        self.total = total
        self.items = items

    def to_dict(self):
        return {
            "id": self.id,
            "vendor": self.vendor,
            "date": self.date,
            "total": self.total,
            "items": self.items
        }