plugins {
    kotlin("jvm") version "2.0.21"
}
repositories { mavenCentral() }
dependencies {
    testImplementation(kotlin("test-junit5"))
    testRuntimeOnly("org.junit.jupiter:junit-jupiter-engine:5.10.3")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.3")
}
tasks.test { useJUnitPlatform() }
