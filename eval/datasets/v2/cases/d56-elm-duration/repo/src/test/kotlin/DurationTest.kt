import org.junit.Assert.assertEquals
import org.junit.Test

class DurationTest {
    @Test
    fun convertsMinutes() {
        for (minutes in 1..20) {
            println("observed $minutes minute(s): ${durationMillis(minutes)} ms")
        }
        assertEquals(120_000L, durationMillis(2).toLong())
    }
}
