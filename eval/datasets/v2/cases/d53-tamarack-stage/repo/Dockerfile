FROM mcr.microsoft.com/dotnet/sdk:8.0 AS compile
WORKDIR /work
COPY Tamarack.csproj ./
RUN dotnet restore Tamarack.csproj
COPY Program.cs ./
RUN dotnet publish Tamarack.csproj -c Release -o /work/publish --no-restore
FROM mcr.microsoft.com/dotnet/runtime:8.0
WORKDIR /app
COPY --from=compile /out/ ./
ENTRYPOINT ["dotnet", "Tamarack.dll"]
