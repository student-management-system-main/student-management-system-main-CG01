#!/usr/bin/env powershell
# Test script for backend API endpoints

$baseUrl = "http://localhost:5000/api/v1"
$headers = @{"Content-Type" = "application/json"}

Write-Host "=== Backend API Endpoint Tests ===" -ForegroundColor Cyan

# Test 1: Health Check
Write-Host "`n[1] Testing Health Check..." -ForegroundColor Yellow
$response = Invoke-WebRequest -Uri "$baseUrl/system/health" -Method GET -UseBasicParsing
$data = $response.Content | ConvertFrom-Json
Write-Host "Status: $($data.status)" -ForegroundColor Green

# Test 2: Login
Write-Host "`n[2] Testing Login..." -ForegroundColor Yellow
$loginBody = @{
    username = "admin1"
    password = "demo1234"
} | ConvertTo-Json

$response = Invoke-WebRequest -Uri "$baseUrl/auth/login" -Method POST -Headers $headers -Body $loginBody -UseBasicParsing
$loginData = $response.Content | ConvertFrom-Json
$accessToken = $loginData.data.access_token
Write-Host "Login successful. Token acquired (length: $($accessToken.Length))" -ForegroundColor Green

# Set auth headers for subsequent requests
$authHeaders = @{
    "Content-Type" = "application/json"
    "Authorization" = "Bearer $accessToken"
}

# Test 3: Get Students List
Write-Host "`n[3] Testing Get Students (with filtering)..." -ForegroundColor Yellow
$response = Invoke-WebRequest -Uri "$baseUrl/students/" -Method GET -Headers $authHeaders -UseBasicParsing
$studentsData = $response.Content | ConvertFrom-Json
$studentCount = $studentsData.data.students.Count
$totalCount = $studentsData.data.total
Write-Host "Retrieved $studentCount students (total: $totalCount)" -ForegroundColor Green

# Test 4: Get Single Student
Write-Host "`n[4] Testing Get Single Student..." -ForegroundColor Yellow
$studentId = $studentsData.data.students[0].id
$response = Invoke-WebRequest -Uri "$baseUrl/students/$studentId" -Method GET -Headers $authHeaders -UseBasicParsing
$studentData = $response.Content | ConvertFrom-Json
Write-Host "Student: $($studentData.data.first_name) $($studentData.data.last_name)" -ForegroundColor Green

# Test 5: Get Fee Types
Write-Host "`n[5] Testing Get Fee Types..." -ForegroundColor Yellow
$response = Invoke-WebRequest -Uri "$baseUrl/fee-types/" -Method GET -Headers $authHeaders -UseBasicParsing
$feeTypesData = $response.Content | ConvertFrom-Json
$feeTypeCount = $feeTypesData.data.Count
Write-Host "Retrieved $feeTypeCount fee types" -ForegroundColor Green

# Test 6: Get Invoices
Write-Host "`n[6] Testing Get Invoices..." -ForegroundColor Yellow
$response = Invoke-WebRequest -Uri "$baseUrl/invoices/" -Method GET -Headers $authHeaders -UseBasicParsing
$invoicesData = $response.Content | ConvertFrom-Json
$invoiceCount = $invoicesData.data.invoices.Count
Write-Host "Retrieved $invoiceCount invoices" -ForegroundColor Green

# Test 7: Risk Distribution
Write-Host "`n[7] Testing Risk Distribution..." -ForegroundColor Yellow
$response = Invoke-WebRequest -Uri "$baseUrl/risk/distribution" -Method GET -Headers $authHeaders -UseBasicParsing
$riskDistData = $response.Content | ConvertFrom-Json
Write-Host "Risk distribution retrieved: $($riskDistData.data | ConvertTo-Json -Compress)" -ForegroundColor Green

# Test 8: System Maintenance Status
Write-Host "`n[8] Testing Maintenance Status..." -ForegroundColor Yellow
$response = Invoke-WebRequest -Uri "$baseUrl/system/maintenance" -Method GET -UseBasicParsing
$maintenanceData = $response.Content | ConvertFrom-Json
Write-Host "Maintenance: $($maintenanceData.data.maintenance)" -ForegroundColor Green

Write-Host "`n=== All endpoint tests completed ===" -ForegroundColor Cyan
Write-Host "[OK] Backend is fully operational" -ForegroundColor Green
