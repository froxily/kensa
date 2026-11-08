import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class LabelContractTest {
    @Test void trimsLeft() { assertEquals("a", LabelPolicy.clean(" a")); }
    @Test void trimsRight() { assertEquals("b", LabelPolicy.clean("b ")); }
    @Test void trimsBoth() { assertEquals("c", LabelPolicy.clean(" c ")); }
    @Test void keepsInside() { assertEquals("d e", LabelPolicy.clean(" d e ")); }
    @Test void keepsHyphen() { assertEquals("f-g", LabelPolicy.clean("f-g")); }
    @Test void acceptsEmpty() { assertEquals("", LabelPolicy.clean("")); }
    @Test void acceptsDigit() { assertEquals("7", LabelPolicy.clean("7")); }
    @Test void stripsTabs() { assertEquals("h", LabelPolicy.clean("\th\t")); }
    @Test void configuredLabel() { assertFalse(LabelPolicy.fromEnvironment().isEmpty()); }
}
