// Time of the steps of SimplePIR's client Query (their functions, unmodified; 64-byte records, 1 GiB,
// m = 30339 columns). Usage: (after ./run_simplepir.sh has cloned simplepir/) go run .
package main

import (
	"fmt"
	"time"

	"github.com/ahenzinger/simplepir/pir"
)

func main() {
	pi := pir.SimplePIR{}
	N, d := uint64(1)<<24, uint64(512)
	p := pi.PickParams(N, d, 1<<10, 32)
	info := pir.SetupDB(N, d, &p).Info
	info.Basis, info.Squishing = 10, 3 // as set by Squish() in their Setup
	shared := pi.Init(info, p)
	A := shared.Data[0]
	fmt.Printf("A: %d x %d uint32 = %.0f MB\n", A.Rows, A.Cols, float64(A.Rows*A.Cols*4)/1e6)
	for r := 0; r < 6; r++ {
		t0 := time.Now()
		secret := pir.MatrixRand(p.N, 1, p.Logq, 0)
		t1 := time.Now()
		err := pir.MatrixGaussian(p.M, 1)
		t2 := time.Now()
		q := pir.MatrixMul(A, secret)
		t3 := time.Now()
		q.MatrixAdd(err)
		t4 := time.Now()
		_, _ = pi.Query(0, shared, p, info)
		t5 := time.Now()
		fmt.Printf("secret %.2f ms  gaussian %.2f ms  A*secret %.2f ms  add %.2f ms  | full Query %.2f ms\n",
			ms(t1.Sub(t0)), ms(t2.Sub(t1)), ms(t3.Sub(t2)), ms(t4.Sub(t3)), ms(t5.Sub(t4)))
	}
}

func ms(d time.Duration) float64 { return float64(d.Microseconds()) / 1e3 }
