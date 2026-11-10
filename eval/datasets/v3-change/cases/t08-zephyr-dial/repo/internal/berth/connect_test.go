package berth

import (
	"database/sql"
	"testing"

	_ "github.com/lib/pq"
)

func TestBerthConnection(t *testing.T) {
	db, err := sql.Open("postgres", connectionString())
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	if err := db.Ping(); err != nil {
		t.Fatal(err)
	}
}
