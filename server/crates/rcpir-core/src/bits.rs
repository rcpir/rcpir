//! MSB-first packing of `F_2` vectors (`docs/db_format.md` §3): element `8b+k` is bit `7-k` of
//! byte `b`; unused trailing bits of the last byte are zero.

/// Bit `i` of a packed vector. `0x80` is the most significant bit of a byte, i.e. element
/// `8b` of byte `b`; element `8b+k` is `0x80 >> k`.
#[inline]
pub fn get_bit(buf: &[u8], i: usize) -> bool {
    buf[i / 8] & (0x80 >> (i % 8)) != 0
}

/// Mask of the last byte of a packed `t`-bit vector that keeps elements `< t`: its top
/// `t mod 8` bits, or all 8 bits (`0xFF`) when `8 | t`.
pub fn tail_mask(t: usize) -> u8 {
    0xFF << ((8 - t % 8) % 8)
}

/// True if `q` is a valid packed vector in `F_2^t`: `ceil(t/8)` bytes, unused trailing bits zero.
pub fn is_well_formed(q: &[u8], t: usize) -> bool {
    q.len() == t.div_ceil(8) && q.last().is_none_or(|&b| b & !tail_mask(t) == 0)
}
