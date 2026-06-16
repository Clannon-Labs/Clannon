use std::time::Instant;

static mut SINK: u64 = 0;

fn main() {
    const N: u64 = 1_000_000_000;

    let mut sum: u64 = 0;

    let start = Instant::now();

    for i in 0..N {
        sum = sum.wrapping_add((i.wrapping_mul(17)) ^ (i >> 3));
    }

    let elapsed = start.elapsed();

    unsafe {
        std::ptr::write_volatile(&raw mut SINK, sum);
    }
    println!("Rust:\n");
    println!("sum = {}", sum);
    println!("time = {:.6} s", elapsed.as_secs_f64());
}