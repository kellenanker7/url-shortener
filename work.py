chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
base = len(chars)


def id_to_short_url(url_db_id):
    short_url = ""

    while url_db_id > 0:
        short_url += chars[url_db_id % base]
        url_db_id //= base

    return short_url[::-1]


def short_url_to_id(short_url):
    short_url_id = 0

    for i in short_url:
        val_i = ord(i)

        if val_i >= ord("a") and val_i <= ord("z"):
            short_url_id = short_url_id * base + val_i - ord("a")

        elif val_i >= ord("A") and val_i <= ord("Z"):
            short_url_id = short_url_id * base + val_i - ord("Z") + 26

        else:
            short_url_id = short_url_id * base + val_i - ord("0") + 52

    return short_url_id


url_db_id = 1234567890
print(id_to_short_url(url_db_id))
print(short_url_to_id(id_to_short_url(url_db_id)))
