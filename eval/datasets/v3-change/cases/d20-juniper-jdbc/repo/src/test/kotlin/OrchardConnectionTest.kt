import java.sql.DriverManager
import kotlin.test.Test
import kotlin.test.assertEquals

class OrchardConnectionTest {
    @Test
    fun readsServerValue() {
        DriverManager.getConnection(System.getProperty("juniper.db.url"), "juniper", "").use { connection ->
            connection.createStatement().executeQuery("SELECT 1").use { result ->
                result.next()
                assertEquals(1, result.getInt(1))
            }
        }
    }
}
