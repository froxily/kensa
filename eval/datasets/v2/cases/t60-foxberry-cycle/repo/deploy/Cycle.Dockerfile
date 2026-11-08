FROM mcr.microsoft.com/dotnet/sdk:8.0 AS package
WORKDIR /app
COPY --from=package /build/publish /app
ENTRYPOINT ["dotnet", "Foxberry.dll"]
