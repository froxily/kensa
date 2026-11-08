import java.io.File

val batches = File("staging/deliveries.list").readLines()
batches.forEach { println("prepared delivery $it") }
val callback = System.getenv("CALAMINT_CALLBACK")
require(!callback.isNullOrBlank()) { "CALAMINT_CALLBACK is empty" }
println("callback: $callback; deliveries: ${batches.size}")
