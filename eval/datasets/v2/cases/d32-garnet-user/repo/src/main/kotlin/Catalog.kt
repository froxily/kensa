import java.sql.DriverManager

fun main() {
    println("Opening catalog connection")
    DriverManager.getConnection(
        "jdbc:postgresql://127.0.0.1:5432/garnet_archive", "postgres", ""
    ).use { connection ->
        connection.createStatement().use { statement ->
            statement.executeQuery("SELECT 1").use { result ->
                result.next()
                println("Catalog probe: ${result.getInt(1)}")
            }
        }
    }
}
