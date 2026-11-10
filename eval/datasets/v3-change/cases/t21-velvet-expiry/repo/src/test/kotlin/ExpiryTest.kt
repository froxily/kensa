import kotlin.test.Test
import kotlin.test.assertEquals

class ExpiryTest {
    @Test fun clampsExpiredValue() {
        assertEquals(-1, expiryDays(-1))
    }
}
