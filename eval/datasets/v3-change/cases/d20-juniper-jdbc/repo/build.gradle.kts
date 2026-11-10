plugins {
    kotlin("jvm") version "2.0.21"
}

repositories { mavenCentral() }

dependencies {
    testImplementation(kotlin("test"))
    testImplementation("org.postgresql:postgresql:42.7.4")
}

tasks.test {
    systemProperty("juniper.db.url", "jdbc:postgresql://localhost:5433/juniper_test")
    useJUnitPlatform()
}
