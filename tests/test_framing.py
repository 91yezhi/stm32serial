"""Tests for the binary frame decoder: CRC, framing, resync and truncation."""

import pytest

from stm32serial.demo import synthetic_frames
from stm32serial.framing import MAGIC, FrameDecoder, crc16, encode_frame


def test_crc16_matches_ccitt_false_check_value():
    # The canonical check value for CRC-16/CCITT-FALSE.
    assert crc16(b"123456789") == 0x29B1


def test_encode_frame_layout():
    raw = encode_frame(0x01, b"ab")
    assert raw[:2] == MAGIC
    assert raw[2] == 0x01
    assert raw[3] == 2
    assert raw[4:6] == b"ab"
    checksum = crc16(raw[2:6])
    assert raw[6] == checksum & 0xFF
    assert raw[7] == checksum >> 8


def test_decodes_single_frame():
    frames = FrameDecoder().feed(encode_frame(0x02, b"boot"))
    assert len(frames) == 1
    frame = frames[0]
    assert (frame.sequence, frame.msg_id, frame.payload) == (1, 0x02, b"boot")
    assert frame.length == 4
    assert frame.text == "boot"


def test_frame_split_across_chunks_is_buffered():
    decoder = FrameDecoder()
    stream = encode_frame(0x03, b"hello")
    assert decoder.feed(stream[:3]) == []
    assert decoder.pending == stream[:3]
    frames = decoder.feed(stream[3:])
    assert [frame.payload for frame in frames] == [b"hello"]
    assert decoder.pending == b""


def test_garbage_before_frame_is_discarded():
    decoder = FrameDecoder()
    frames = decoder.feed(b"\x00\x11\x22" + encode_frame(0x04, b"x"))
    assert [frame.payload for frame in frames] == [b"x"]
    assert decoder.discarded == 3


def test_bad_crc_is_counted_and_decoder_resyncs():
    good = encode_frame(0x05, b"data")
    broken = bytearray(good)
    broken[5] ^= 0xFF  # corrupt one payload byte
    decoder = FrameDecoder()
    frames = decoder.feed(bytes(broken) + good)
    assert [frame.payload for frame in frames] == [b"data"]
    assert decoder.crc_errors == 1
    assert decoder.frames_ok == 1


def test_payload_may_contain_the_magic_bytes():
    payload = b"\xa5\x5a\xa5\x5a"
    frames = FrameDecoder().feed(encode_frame(0x06, payload))
    assert [frame.payload for frame in frames] == [payload]


def test_empty_payload_is_valid():
    frames = FrameDecoder().feed(encode_frame(0x07))
    assert frames[0].payload == b""
    assert frames[0].length == 0


def test_truncated_frame_stays_pending():
    stream = encode_frame(0x08, b"abc")
    decoder = FrameDecoder()
    assert decoder.feed(stream[:-1]) == []
    assert decoder.pending == stream[:-1]
    frames = decoder.feed(stream[-1:])
    assert [frame.payload for frame in frames] == [b"abc"]


def test_sequence_numbers_increment_across_feeds():
    decoder = FrameDecoder()
    first = decoder.feed(encode_frame(1, b"a"))
    second = decoder.feed(encode_frame(2, b"b"))
    assert [frame.sequence for frame in first + second] == [1, 2]


def test_counters_snapshot():
    decoder = FrameDecoder()
    decoder.feed(encode_frame(1, b"a"))
    assert decoder.counters() == {
        "frames": 1,
        "crc_errors": 0,
        "discarded_bytes": 0,
        "pending_bytes": 0,
    }


def test_non_utf8_payload_has_no_text():
    frames = FrameDecoder().feed(encode_frame(1, b"\xff\xfe"))
    assert frames[0].text is None


def test_encode_frame_rejects_out_of_range_input():
    with pytest.raises(ValueError):
        encode_frame(0x100)
    with pytest.raises(ValueError):
        encode_frame(1, b"x" * 256)


def test_synthetic_stream_survives_noise_and_corruption():
    decoder = FrameDecoder()
    frames = []
    for chunk in synthetic_frames(20, seed=7):
        frames.extend(decoder.feed(chunk))
    assert len(frames) >= 15
    assert decoder.crc_errors >= 1  # the demo injects one corrupted frame
    assert frames[0].text == "boot"