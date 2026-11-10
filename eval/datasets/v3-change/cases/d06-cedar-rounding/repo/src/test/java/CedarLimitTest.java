import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;
class CedarLimitTest {
    @Test void includesBoundary() { assertTrue(CedarLimit.eligible(100)); }
}
