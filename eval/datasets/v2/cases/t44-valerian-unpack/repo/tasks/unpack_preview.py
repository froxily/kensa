import resource
import struct
import traceback

resource.setrlimit(resource.RLIMIT_AS, (96 * 1024 * 1024, 96 * 1024 * 1024))
with open('tasks/preview-items.txt', encoding='utf-8') as items:
    for item in items:
        print('queued preview:', item.strip(), flush=True)
try:
    buffer = bytearray(128 * 1024 * 1024)
except MemoryError:
    traceback.print_exc()
    buffer = None
print(struct.unpack_from('<I', buffer)[0])
