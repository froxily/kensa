package queue

import (
 "context"
 "testing"
 "github.com/redis/go-redis/v9"
)
func TestPing(t *testing.T) {
 c := redis.NewClient(&redis.Options{Addr: "localhost:6379"})
 defer c.Close()
 if err := c.Ping(context.Background()).Err(); err != nil { t.Fatal(err) }
}
