-- Tạo database dùng cho test (api/tests/conftest.py trỏ mặc định tới đây).
-- Chỉ chạy tự động khi volume dữ liệu của postgres còn TRỐNG (lần "docker
-- compose up" đầu tiên trên một máy) — xem README, mục Test.
CREATE DATABASE file_understanding_test;
