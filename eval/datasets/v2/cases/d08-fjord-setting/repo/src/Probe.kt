fun main() {
    val region = requireNotNull(System.getenv("FJORD_REGION")) { "FJORD_REGION is required" }
    println("region: $region")
}
