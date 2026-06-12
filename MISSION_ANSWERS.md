# Day 12 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Các anti-pattern được tìm thấy trong file basic app.py
1. **Hardcoded Secrets (Lộ thông tin nhạy cảm)**: API key (`OPENAI_API_KEY`) và thông tin kết nối cơ sở dữ liệu (`DATABASE_URL`) bị khai báo trực tiếp (hardcode) trong mã nguồn. Nếu đẩy code này lên một kho chứa công khai như GitHub, các thông tin này sẽ lập tức bị lộ.
2. **Không có hệ thống quản lý cấu hình (Config Management)**: Các tham số cấu hình như (`DEBUG = True`, `MAX_TOKENS = 500`) bị viết cứng, không thể linh hoạt thay đổi giữa các môi trường khác nhau (như dev, staging, hay production).
3. **Ghi log không đúng chuẩn**: Sử dụng các câu lệnh `print()` thông thường thay vì một thư viện ghi log chuyên dụng, đồng thời ghi đè và in cả thông tin nhạy cảm (`OPENAI_API_KEY`) ra stdout.
4. **Thiếu các endpoint kiểm tra trạng thái (Health / Readiness Probes)**: Ứng dụng không cung cấp endpoint `/health` hoặc `/ready`. Hệ thống triển khai (deployment platform) không thể tự động phát hiện nếu container bị treo hoặc lỗi để thực hiện restart.
5. **Cố định địa chỉ IP và Port (Host & Port)**: Ứng dụng liên kết cố định với `localhost` và cổng `8000`, đồng thời kích hoạt mặc định `reload=True`. Điều này ngăn cản việc nhận traffic từ bên ngoài khi chạy trong container và gây hao phí hiệu năng không đáng có trong môi trường production.

### Exercise 1.2: Chạy phiên bản cơ bản (Basic Version)
- Đã cài đặt dependencies thông qua `pip install -r requirements.txt` và khởi chạy thành công ứng dụng cơ bản bằng lệnh `python app.py`. 
- Ứng dụng chạy tốt trên localhost nhưng chưa đủ tiêu chuẩn vận hành thực tế (production-ready) vì thiếu khả năng tự khôi phục, bảo mật thông tin và tính năng quản lý tài nguyên.

### Exercise 1.3: Bảng so sánh giữa hai phiên bản

| Tính năng | Phát triển (Basic) | Môi trường production (Advanced) | Tại sao quan trọng? |
|---------|-----------------|-----------------------|----------------|
| Cấu hình (Config) | Viết cứng trong code | Sử dụng biến môi trường (Environment variables - chuẩn 12-Factor) | Giúp chạy cùng một bản build trên nhiều môi trường khác nhau mà không cần sửa code, giữ bảo mật cho các API key/secrets. |
| Kiểm tra sức khỏe (Health check) | Không có | Cung cấp endpoint `/health` & `/ready` | Cần thiết cho các nền tảng điều phối (Docker Compose, Kubernetes, Railway) kiểm tra xem container còn hoạt động tốt và sẵn sàng nhận request hay chưa. |
| Ghi log (Logging) | Lệnh `print()` thô | Định dạng cấu trúc JSON | Giúp các hệ thống thu thập log tập trung (Datadog, ELK, Loki) dễ dàng phân tích, lọc và tìm kiếm thông tin nhanh chóng. |
| Tắt ứng dụng (Shutdown) | Tắt đột ngột (kill) | Tắt an toàn (Graceful shutdown qua signal SIGTERM) | Đảm bảo các kết nối đến DB/Redis được đóng an toàn và các request đang xử lý dở được hoàn thành trước khi tiến trình kết thúc. |

---

## Part 2: Docker

### Exercise 2.1: Các câu hỏi về Dockerfile cơ bản
1. **Base image là gì?**: Base image được sử dụng là `python:3.11`, chứa đầy đủ hệ điều hành Debian cùng với môi trường Python 3.11 và các công cụ biên dịch đi kèm (~1 GB).
2. **Working directory là gì?**: Thư mục làm việc trong container được đặt là `/app`. Mọi câu lệnh tiếp theo sẽ chạy tương đối so với thư mục này.
3. **Tại sao COPY requirements.txt trước?**: Để tận dụng cơ chế lưu cache layer của Docker. Khi source code thay đổi nhưng danh sách dependencies không đổi, Docker sẽ bỏ qua bước chạy `pip install`, giúp tối ưu thời gian build đáng kể.
4. **CMD vs ENTRYPOINT khác nhau thế nào?**: `ENTRYPOINT` định nghĩa câu lệnh cố định luôn chạy khi container start (ví dụ: `python`). `CMD` cung cấp các đối số mặc định truyền vào lệnh này, và các đối số của `CMD` dễ dàng bị ghi đè khi ta chạy lệnh từ terminal ngoài.

### Exercise 2.2: Build và chạy container cơ bản
- Đã thực hiện build thành công container cơ bản thông qua lệnh:
  ```bash
  docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
  ```
- **Kích thước Image**: Có kích thước rất nặng khoảng **~1.02 GB** do chứa đầy đủ bộ công cụ biên dịch của hệ điều hành.

### Exercise 2.3: Multi-stage build (Tối ưu hóa image)
- **Stage 1 (Builder) làm gì?**: Sử dụng ảnh `python:3.11-slim` làm môi trường tạm, cài đặt các thư viện hệ thống cần thiết (gcc, libpq-dev) để cài đặt và biên dịch các python packages vào thư mục `/root/.local`.
- **Stage 2 (Runtime) làm gì?**: Khởi tạo từ ảnh `python:3.11-slim` sạch, tạo user không có quyền quản trị (appuser), copy thư viện đã biên dịch hoàn chỉnh từ Stage 1 sang `/home/appuser/.local`, copy mã nguồn và thiết lập chạy ứng dụng với quyền của `appuser`.
- **Tại sao image nhỏ hơn?**: Vì Stage 2 hoàn toàn loại bỏ các file tạm, cache của pip và các công cụ biên dịch cồng kềnh (gcc, compiler headers), chỉ chứa tài nguyên chạy trực tiếp, giúp rút gọn kích thước chỉ còn **~150-200 MB** (giảm ~80-85%).

### Exercise 2.4: Sơ đồ kiến trúc Nginx Load Balancer và liên kết Docker Compose
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
- **Các service khởi động**: Bao gồm 3 container `agent` chạy song song làm nhiệm vụ tính toán, 1 container `redis` dùng để chia sẻ session, và 1 container `nginx` làm Load Balancer.
- **Phương thức giao tiếp**: Client kết nối trực tiếp đến Nginx (cổng 80/8080). Nginx đóng vai trò proxy điều phối request tuần tự (Round-Robin) đến các container agent. Do các container agent không giữ state cục bộ trong bộ nhớ RAM (Stateless), chúng đồng bộ dữ liệu người dùng trực tiếp bằng cách kết nối chung đến container `redis` thông qua mạng ảo nội bộ.

---

## Part 3: Cloud Deployment

### Exercise 3.1: Triển khai ứng dụng lên cloud qua Railway
- **URL hoạt động**: `https://distinguished-reverence-production-a4e9.up.railway.app`
- **Ảnh chụp dashboard**: Đã lưu trữ và liên kết trong repo tại thư mục [screenshots/dashboard.png](screenshots/dashboard.png).

### Exercise 3.2: So sánh `render.yaml` và `railway.toml`
- **`railway.toml`**: Là file cấu hình nhẹ dùng cho Railway CLI, chủ yếu mô tả cách build (sử dụng Dockerfile hoặc buildpacks), các pattern cần theo dõi thay đổi và cấu hình khởi chạy cơ bản.
- **`render.yaml` (Render Blueprints)**: Là tệp tin dạng Infrastructure as Code (IaC) toàn diện hơn. Nó định nghĩa cấu trúc toàn hệ thống trên Render, cho phép khai báo kiểu dịch vụ (Web Service, Redis, DB), cấu hình tài nguyên (starter plan), vị trí máy chủ (singapore region), và thiết lập tự động hóa biến môi trường bảo mật (`generateValue: true`).

### Exercise 3.3: Hiểu cấu trúc CI/CD trong GCP Cloud Run
- **`cloudbuild.yaml` (CI pipeline)**: Định nghĩa các bước tự động hóa khi có code mới: build docker image, gắn thẻ phiên bản (tagging) và đẩy (push) image đó lên Artifact Registry trên Google Cloud.
- **`service.yaml` (CD configuration)**: Khai báo tài nguyên hệ thống mong muốn cho Cloud Run (CPU, RAM, số lượng replica, cổng mạng, biến môi trường). Cloud Run sẽ đọc tệp này để tự động cập nhật trạng thái hoạt động của container trên Cloud mà không cần thao tác thủ công trên console.

---

## Part 4: API Security

### Exercise 4.1: API Key authentication
- **Kiểm tra ở đâu?**: Tiêu đề API key được kiểm tra tại hàm `verify_api_key` nằm trong Middleware/Dependency Injection của route, cụ thể qua tiêu đề `X-API-Key`.
- **Nếu sai API Key?**: Ném lỗi `HTTPException` với mã trạng thái `401 Unauthorized` và thông báo lỗi rõ ràng cho client.
- **Cách xoay vòng (rotate) key**: Cập nhật giá trị biến môi trường `AGENT_API_KEY` trên dashboard quản lý của hosting (Railway/Render). Nền tảng sẽ tự động reload các container để nhận key bảo mật mới mà không cần sửa đổi mã nguồn.

### Exercise 4.2: Cơ chế xác thực JWT
1. Client gửi credentials (username/password) đến `/token` qua phương thức POST.
2. Server xác minh thông tin. Nếu hợp lệ, server tạo một mã token JWT chứa các thông tin công khai (username, thời gian hết hạn) và ký điện tử bằng thuật toán đối xứng HMAC-SHA256 sử dụng khóa bí mật `JWT_SECRET`.
3. Client lưu token và gửi kèm trong tiêu đề `Authorization: Bearer <TOKEN>` ở mọi request tiếp theo.
4. Server nhận request giải mã token bằng khóa bí mật, kiểm tra tính hợp lệ và thời gian hết hạn để cho phép hoặc từ chối request.

### Exercise 4.3: Cơ chế Rate Limiting
- **Thuật toán sử dụng**: Sliding Window Counter sử dụng bộ đếm thời gian (timestamps) của request lưu trong bộ nhớ hoặc Redis.
- **Giới hạn cấu hình**: Mặc định giới hạn ở mức **10 requests / phút** cho tài khoản user thường và 100 requests / phút cho admin.
- **Bypass cho admin**: Phân quyền người dùng dựa trên API key hoặc token nhận diện, định tuyến admin tới singleton limiter khác (`rate_limiter_admin`) hoặc trả về cho phép ngay lập tức mà không ghi nhận timestamp.

### Exercise 4.4: Cách triển khai Cost Guard
- Chi phí API của người dùng được theo dõi thông qua Redis bằng key `cost:{user_id}:{date}`. Khi có request đến, hệ thống ước tính chi phí cho request đó dựa trên độ dài văn bản câu hỏi (đầu vào: \$0.00015 / 1K tokens; đầu ra: \$0.0006 / 1K tokens). Nếu chi phí tích lũy trong ngày/tháng vượt quá hạn mức (\$5.0 hoặc \$10.0/user), hệ thống sẽ ném ra ngoại lệ `402 Payment Required` để chặn gọi API LLM tốn kém.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Sự khác biệt của Health Checks
- **Liveness probe (`/health`)**: Trả lời câu hỏi "Container có còn sống không?". Nếu endpoint này trả về mã lỗi (non-200), nền tảng hosting sẽ coi tiến trình chính bị treo/lỗi và lập tức khởi động lại container.
- **Readiness probe (`/ready`)**: Trả lời câu hỏi "Container đã sẵn sàng nhận request chưa?". Nó kiểm tra kết nối cơ sở dữ liệu và Redis. Nếu trả về lỗi (503), load balancer sẽ tạm thời loại container này ra khỏi hàng đợi nhận traffic để tránh gây lỗi cho client.

### Exercise 5.2: Graceful Shutdown vận hành ra sao?
- Khi tiến trình nhận tín hiệu `SIGTERM` từ container orchestrator, handler sẽ bắt tín hiệu, cập nhật biến `is_ready` thành `False` để ứng dụng phản hồi lỗi `503` đối với các kiểm tra sức khỏe của load balancer (ngừng nhận traffic mới). Đồng thời, tiến trình chờ tối đa 30 giây để hoàn thành nốt các request dài (long-task) đang xử lý dở trước khi ngắt kết nối DB/Redis và kết thúc an toàn.

### Exercise 5.3: Tầm quan trọng của Thiết kế Stateless
- Khi mở rộng hệ thống lên nhiều instances, load balancer sẽ chuyển tiếp các request của cùng một người dùng tới các container khác nhau. Nếu lưu trữ history hay session cục bộ trong RAM của container, các request sau sẽ mất toàn bộ ngữ cảnh trước đó.
- Bằng cách sử dụng thiết kế **Stateless** (lưu trữ toàn bộ session và history vào Redis chung), mọi container đều có thể đọc/ghi trạng thái người dùng như nhau, giúp mở rộng hoặc thu hẹp hệ thống cực kỳ dễ dàng.

### Exercise 5.4 & 5.5: Kiểm thử Load Balancing và Stateless
- Chạy hệ thống với 3 instance agent và 1 Nginx load balancer. Khi dùng script kiểm thử gửi liên tiếp nhiều request và thực hiện tắt ngẫu nhiên 1 container agent:
  - Nginx tự động phát hiện container die và chuyển tiếp request tới các container còn lại.
  - Do history cuộc trò chuyện được lưu trữ tập trung tại Redis, cuộc hội thoại của người dùng vẫn tiếp diễn mượt mà, không bị mất ngữ cảnh (nhớ được tên người dùng là Alice xuyên suốt cuộc hội thoại).
