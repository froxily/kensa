package queue

// Dispatch hands a value to the worker and returns it.
func Dispatch(value int) int {
    ch := make(chan int)
    ch <- value
    return <-ch
}

// A receiver must be running before an unbuffered send.
