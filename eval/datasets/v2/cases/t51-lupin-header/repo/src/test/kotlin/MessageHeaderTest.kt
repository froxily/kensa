import org.junit.Assert.assertEquals
import org.junit.Test

private fun header(message: String): String = message.substringBefore(' ')

class MessageHeaderTest {
    @Test fun keepsQuotaPhrase() { assertEquals("storage quota exceeded", header("storage quota exceeded: archive")) }
    @Test fun wordAlpha() { assertEquals("alpha", header("alpha")) }
    @Test fun wordBeta() { assertEquals("beta", header("beta")) }
    @Test fun wordGamma() { assertEquals("gamma", header("gamma")) }
    @Test fun wordDelta() { assertEquals("delta", header("delta")) }
    @Test fun wordEpsilon() { assertEquals("epsilon", header("epsilon")) }
    @Test fun wordZeta() { assertEquals("zeta", header("zeta")) }
    @Test fun wordEta() { assertEquals("eta", header("eta")) }
    @Test fun wordTheta() { assertEquals("theta", header("theta")) }
    @Test fun wordIota() { assertEquals("iota", header("iota")) }
    @Test fun wordKappa() { assertEquals("kappa", header("kappa")) }
}
