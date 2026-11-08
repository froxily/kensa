import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import java.net.HttpURLConnection
import java.net.URI

class GraphQueryTest {
    @Test fun query() {
        val conn = URI("http://127.0.0.1:17474/db/herbarium/tx/commit").toURL().openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/json")
        conn.outputStream.use { it.write(java.io.File("requests/graph-query.json").readBytes()) }
        val status = conn.responseCode
        if (status != 200) println(conn.errorStream.bufferedReader().readText())
        assertEquals(200, status)
    }
}
