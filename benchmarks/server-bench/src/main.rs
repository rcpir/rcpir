//! B2/B3: compute-server throughput, calling `CpuBackend` directly (no HTTP).
//!
//! Random `X` of T * L bytes (contents do not affect the cost) and fresh uniform queries for every
//! pass (`q_c = He + e_i` is pseudorandom). Prints one JSON line per (shape, threads, batch).
//!
//! Usage: server-bench --shapes T1xL1,T2xL2 --threads 1,28 --batch 1,2,4 --reps 20
//! (T = number of columns, L = column bytes). T * L is 1 GiB of records plus the block headers and
//! padding (db_format.md §3), so it may exceed 1 GiB slightly; it must be at least 1 GiB and at most
//! 1 GiB + 1/8. Throughput counts the 1 GiB of records, as SimplePIR counts its database.

use std::time::Instant;

use rand::RngCore;
use rcpir_core::{Backend, CpuBackend};

const DB_BYTES: usize = 1 << 30;

fn list(args: &[String], name: &str) -> Vec<String> {
    let i = args.iter().position(|a| a == name).unwrap_or_else(|| panic!("missing {name}"));
    args[i + 1].split(',').map(String::from).collect()
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let shapes: Vec<(usize, usize)> = list(&args, "--shapes")
        .iter()
        .map(|s| {
            let (t, l) = s.split_once('x').expect("shape is TxL");
            (t.parse().unwrap(), l.parse().unwrap())
        })
        .collect();
    let threads: Vec<usize> = list(&args, "--threads").iter().map(|s| s.parse().unwrap()).collect();
    let batches: Vec<usize> = list(&args, "--batch").iter().map(|s| s.parse().unwrap()).collect();
    let reps: usize = list(&args, "--reps")[0].parse().unwrap();

    for &(t, _) in &shapes {
        assert!(t % 8 == 0, "need 8 | t");
    }
    for &(t, l) in &shapes {
        assert!(t * l >= DB_BYTES && t * l <= DB_BYTES + DB_BYTES / 8, "need 1 GiB <= t * L <= 1 GiB + 1/8");
    }
    let mut rng = rand::rng();
    let max_bytes = shapes.iter().map(|&(t, l)| t * l).max().unwrap();
    let mut x = vec![0u8; max_bytes];
    rng.fill_bytes(&mut x);

    for &(t, l) in &shapes {
        for &th in &threads {
            let backend = CpuBackend::new(x[..t * l].to_vec(), t, l, th, None).unwrap();
            for &k in &batches {
                let mut q = vec![vec![0u8; t / 8]; k];
                let mut out = vec![vec![0u8; l]; k];
                let mut ms = Vec::with_capacity(reps);
                for rep in 0..=reps {
                    q.iter_mut().for_each(|qi| rng.fill_bytes(qi));
                    let qs: Vec<&[u8]> = q.iter().map(|v| v.as_slice()).collect();
                    let mut os: Vec<&mut [u8]> = out.iter_mut().map(|v| v.as_mut_slice()).collect();
                    let start = Instant::now();
                    backend.answer_batch(&qs, &mut os);
                    if rep > 0 {
                        ms.push(start.elapsed().as_secs_f64() * 1e3); // rep 0 is a warm-up
                    }
                }
                let mean = ms.iter().sum::<f64>() / reps as f64;
                let std = (ms.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / reps as f64).sqrt();
                // Throughput as in SimplePIR: database size x queries / time.
                let mib_s = (DB_BYTES >> 20) as f64 * k as f64 / (mean / 1e3);
                println!(
                    "{{\"t\":{t},\"L\":{l},\"threads\":{th},\"batch\":{k},\"reps\":{reps},\"ms_mean\":{mean:.3},\
                     \"ms_std\":{std:.3},\"ms_per_query\":{:.3},\"mib_s\":{mib_s:.0}}}",
                    mean / k as f64
                );
            }
        }
    }
}
