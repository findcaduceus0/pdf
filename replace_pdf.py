import sys
import os
import zlib
import shutil
import tempfile


def replace_in_pdf(path: str, old: bytes, new: bytes) -> int:
    with open(path, 'rb') as f:
        data = f.read()

    changed = False
    search_pos = 0

    while True:
        stream_pos = data.find(b'stream', search_pos)
        if stream_pos == -1:
            break
        endstream_pos = data.find(b'endstream', stream_pos)
        if endstream_pos == -1:
            break

        dict_start = data.rfind(b'<<', 0, stream_pos)
        if dict_start == -1:
            search_pos = endstream_pos + len(b'endstream')
            continue
        dict_bytes = data[dict_start:stream_pos]
        if b'/FlateDecode' not in dict_bytes:
            search_pos = endstream_pos + len(b'endstream')
            continue

        start = stream_pos + len(b'stream')
        if data[start:start+2] == b'\r\n':
            start += 2
        elif data[start:start+1] in (b'\n', b'\r'):
            start += 1

        end = endstream_pos
        if data[end-2:end] == b'\r\n':
            end -= 2
        elif data[end-1:end] in (b'\n', b'\r'):
            end -= 1

        comp = data[start:end]
        try:
            decompressed = zlib.decompress(comp)
        except Exception:
            search_pos = endstream_pos + len(b'endstream')
            continue

        if old not in decompressed:
            search_pos = endstream_pos + len(b'endstream')
            continue

        modified = decompressed.replace(old, new, 1)

        co = zlib.compressobj(level=9, wbits=-15)
        raw = co.compress(modified) + co.flush(zlib.Z_SYNC_FLUSH)

        header = comp[:2] if len(comp) >= 2 else b'\x78\xda'
        trailer = zlib.adler32(modified).to_bytes(4, 'big')
        final_block = b'\x01\x00\x00\xff\xff'

        recompressed = header + raw + final_block + trailer
        diff = len(comp) - len(recompressed)
        if diff < 0 or diff % 5 != 0:
            sys.stderr.write('Replacement would change stream size\n')
            return 2

        padding = b'\x00\x00\x00\xff\xff' * (diff // 5)
        recompressed = header + raw + padding + final_block + trailer

        if len(recompressed) != len(comp):
            sys.stderr.write('Padding error\n')
            return 2

        data = data[:start] + recompressed + data[end:]
        changed = True
        search_pos = endstream_pos + len(b'endstream')

    if not changed:
        sys.stderr.write('String not found\n')
        return 1

    tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path))
    os.write(tmp_fd, data)
    os.close(tmp_fd)
    shutil.copystat(path, tmp_path)
    os.replace(tmp_path, path)
    return 0


def main(argv=None):
    argv = argv or sys.argv
    if len(argv) != 4:
        print('Usage: python replace_pdf.py <file.pdf> <old> <new>')
        return 1
    return replace_in_pdf(argv[1], argv[2].encode('utf-8'), argv[3].encode('utf-8'))


if __name__ == '__main__':
    sys.exit(main())
