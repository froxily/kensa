package berth

import "fmt"

func connectionString() string {
	return fmt.Sprintf("host=127.0.0.1 port=%d user=postgres dbname=berth_test sslmode=disable", 5433)
}
