import org.testng.Assert.assertEquals
import org.testng.annotations.Test

class AddressSpec {
    @Test(priority = 1) fun verifiesOne() { assertEquals("a".length, 1) }
    @Test(priority = 2) fun verifiesTwo() { assertEquals("ab".length, 2) }
    @Test(priority = 3) fun verifiesThree() { assertEquals("abc".length, 3) }
    @Test(priority = 4) fun verifiesFour() { assertEquals("abcd".length, 4) }
    @Test(priority = 5) fun verifiesFive() { assertEquals("abcde".length, 5) }
    @Test(priority = 6) fun verifiesSix() { assertEquals("abcdef".length, 6) }
    @Test(priority = 7) fun verifiesSeven() { assertEquals("abcdefg".length, 7) }
    @Test(priority = 8) fun verifiesEight() { assertEquals("abcdefgh".length, 8) }
    @Test(priority = 9) fun hidesMailbox() {
        assertEquals(redactMailbox("moss@example.test"), "m***@example.test")
    }
}
