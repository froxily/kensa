import time


def run():
    while True:
        print("waiting for work", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    run()
