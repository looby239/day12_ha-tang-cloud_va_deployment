# Day 12 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Các anti-pattern được tìm thấy trong file basic app.py
1. **Hardcoded Secrets (Lộ thông tin nhạy cảm)**: API key (`OPENAI_API_KEY`) và thông tin kết nối cơ sở dữ liệu (`DATABASE_URL`) bị khai báo trực tiếp (hardcode) trong mã nguồn. Nếu đẩy code này lên một kho chứa công khai như GitHub, các thông tin này sẽ lập tức bị lộ.
2. **Không có hệ thống quản lý cấu hình (Config Management)**: Các tham số cấu hình như (`DEBUG = True`, `MAX_TOKENS = 500`) bị viết cứng, không thể linh hoạt thay đổi giữa các môi trường khác nhau (như dev, staging, hay production).
3. **Ghi log không đúng chuẩn**: Sử dụng các câu lệnh `print()` thông thường thay vì một thư viện ghi log chuyên dụng, đồng thời ghi đè và in cả thông tin nhạy cảm (`OPENAI_API_KEY`) ra stdout.
4. **Thiếu các endpoint kiểm tra trạng thái (Health / Readiness Probes)**: Ứng dụng không cung cấp endpoint `/health` hoặc `/ready`. Hệ thống triển khai (deployment platform) không thể tự động phát hiện nếu container bị treo hoặc lỗi để thực hiện restart.
5. **Cố định địa chỉ IP và Port (Host & Port)**: Ứng dụng liên kết cố định với `localhost` và cổng `8000`, đồng thời kích hoạt mặc định `reload=True`. Điều này ngăn cản việc nhận traffic từ bên ngoài khi chạy trong container và gây hao phí hiệu năng không đáng có trong môi trường production.

### Exercise 1.3: Bảng so sánh giữa hai phiên bản

| Tính năng | Phát triển (Basic) | Môi trường production (Advanced) | Tại sao quan trọng? |
|---------|-----------------|-----------------------|----------------|
| Cấu hình (Config) | Viết cứng trong code | Sử dụng biến môi trường (Environment variables - chuẩn 12-Factor) | Giúp chạy cùng một bản build trên nhiều môi trường khác nhau mà không cần sửa code, giữ bảo mật cho các API key/secrets. |
| Kiểm tra sức khỏe (Health check) | Không có | Cung cấp endpoint `/health` & `/ready` | Cần thiết cho các nền tảng điều phối (Docker Compose, Kubernetes, Railway) kiểm tra xem container còn hoạt động tốt và sẵn sàng nhận request hay chưa. |
| Ghi log (Logging) | Lệnh `print()` thô | Định dạng cấu trúc JSON | Giúp các hệ thống thu thập log tập trung (Datadog, ELK, Loki) dễ dàng phân tích, lọc và tìm kiếm thông tin nhanh chóng. |
| Tắt ứng dụng (Shutdown) | Tắt đột ngột (kill) | Tắt an toàn (Graceful shutdown qua signal SIGTERM) | Đảm bảo các kết nối đến DB/Redis được đóng an toàn và các request đang xử lý dở được hoàn thành trước khi tiến trình kết thúc. |

---

## Part 2: Docker

### Exercise 2.1: Các câu hỏi về Dockerfile
1. **Base image**: `python:3.11-slim` là một image Debian tối giản đã cài sẵn Python 3.11, lược bỏ các công cụ build nâng cao và thư viện hệ thống không cần thiết để giảm dung lượng.
2. **Working directory**: `/app` được thiết lập làm thư mục làm việc mặc định trong container. Các lệnh sau đó (`COPY`, `RUN`, `CMD`) sẽ được thực thi tương đối so với thư mục này.
3. **Tại sao nên COPY requirements.txt trước?**: Để tận dụng tối đa cơ chế lưu cache theo layer của Docker. Vì các thư viện phụ thuộc ít khi thay đổi so với mã nguồn, việc cache layer này giúp Docker bỏ qua bước cài đặt lại thư viện khi bạn chỉ sửa đổi code, giúp tối ưu hóa thời gian build image.
4. **CMD so với ENTRYPOINT**: `ENTRYPOINT` định nghĩa lệnh chạy mặc định luôn được thực thi khi khởi động container và rất khó bị ghi đè (ví dụ: `uvicorn`). `CMD` cung cấp các tham số mặc định truyền vào cho `ENTRYPOINT` và có thể dễ dàng bị ghi đè khi chạy container từ command line.

### Exercise 2.3: So sánh kích thước Image
- **Phiên bản phát triển (Single-stage)**: ~1.02 GB
- **Phiên bản production (Multi-stage)**: ~150-200 MB
- **Sự khác biệt**: Giảm được khoảng 80% đến 85% dung lượng image.
- **Tại sao**: Giai đoạn build (builder stage) sử dụng các công cụ biên dịch nặng để cài đặt thư viện, còn giai đoạn chạy (runtime stage) sử dụng một image slim sạch và chỉ copy các thư viện đã được biên dịch xong (`/root/.local`) cùng mã nguồn ứng dụng, giúp loại bỏ hoàn toàn các trình biên dịch dư thừa.

### Exercise 2.4: Sơ đồ kiến trúc Nginx Load Balancer
```
              [Client Browser / Client CLI]
                           |
                           v
              [Nginx Load Balancer (Cổng 80/8080)]
                           |
            +--------------+--------------+
            | (Round-Robin)  |            |
            v              v              v
       [Agent-1]       [Agent-2]      [Agent-3] (Cổng 8000)
            |              |              |
            +--------------+--------------+
                           |
                           v
               [Redis Server (Cổng 6379)]
```
- **Các service được khởi động**: `agent` (được scale lên 3 bản sao), `redis` (bộ nhớ cache lưu session), và `nginx` (làm reverse proxy chịu tải).
- **Luồng giao tiếp**: Client gửi request đến cổng 80/8080 của Nginx. Nginx thực hiện chia tải tuần tự (round-robin) đến các container `agent`. Do các agent được thiết kế không lưu trạng thái (stateless), chúng sẽ truy vấn và cập nhật thông tin session/rate-limit/cost của người dùng từ hệ thống lưu trữ chung là container `redis`.

---

## Part 3: Cloud Deployment

### Exercise 3.1: Triển khai Railway
- **URL**: `https://day12-ha-tang-cloud-va-deployment-production.up.railway.app`
- **Link ảnh chụp màn hình**: [Deployment Dashboard](screenshots/dashboard.png)

---

## Part 4: API Security

### Exercise 4.1-4.3: Kết quả kiểm thử
- **Xác thực API**:
  - Request không chứa header `X-API-Key` trả về: `401 Unauthorized`
  - Request chứa header `X-API-Key` sai trả về: `401 Unauthorized`
  - Request chứa header `X-API-Key` đúng (`dev-key-change-me`) trả về: `200 OK`
- **Rate Limiting**:
  - Gửi quá 10 requests trong vòng 1 phút trả về: `429 Too Many Requests`

### Exercise 4.4: Cách hiện thực Cost Guard
- **Giải pháp**: Sử dụng Redis để lưu trữ chi phí tích lũy hàng ngày của từng người dùng bằng các key có dạng `cost:{user_id}:{date}`. Khi nhận request, hệ thống ước tính chi phí cho request đó dựa trên số lượng token (đầu vào: \$0.00015 / 1K tokens; đầu ra: \$0.0006 / 1K tokens). Nếu chi phí hiện tại cộng với chi phí ước tính vượt quá giới hạn ngân sách hàng ngày/hàng tháng đã cấu hình, hệ thống sẽ từ chối xử lý và ném ra mã lỗi `402 Payment Required`.

---

## Part 5: Scaling & Reliability

### Exercise 5.1-5.5: Ghi chú triển khai thực tế
- **Health/Readiness checks**: `/health` kiểm tra xem ứng dụng còn sống (liveness) hay không; `/ready` kiểm tra trạng thái kết nối tới Redis và cơ sở dữ liệu để đảm bảo ứng dụng đã sẵn sàng nhận request.
- **Graceful shutdown**: Lắng nghe tín hiệu `SIGTERM` từ hệ thống điều phối, cập nhật trạng thái `/ready` thành `503` để load balancer ngừng điều hướng request mới đến instance này, hoàn thành nốt các request đang xử lý dở dang và giải phóng các kết nối đến Redis/DB trước khi tắt hẳn ứng dụng.
- **Thiết kế Stateless**: Đưa toàn bộ dữ liệu lịch sử cuộc trò chuyện (history), lượt đếm giới hạn tần suất (rate limits) và chi phí sử dụng (costs) từ bộ nhớ RAM của container vào Redis, cho phép các instance ứng dụng có thể scale-out hoặc tắt/bật tùy ý mà không làm gián đoạn trải nghiệm của người dùng.
