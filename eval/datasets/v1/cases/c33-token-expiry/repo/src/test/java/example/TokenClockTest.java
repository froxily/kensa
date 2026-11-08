package example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class TokenClockTest {
    @Test void expiresAtBoundary() {
        assertFalse(TokenClock.isValid(100, 100));
    }
    @Test void validBeforeBoundary() {
        assertTrue(TokenClock.isValid(99, 100));
    }
}
