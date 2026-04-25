# Dev-guide.md — Development Guide

## 1. Coding Rules

- Không viết logic trong UI widget
- Domain phải thuần Python
- Controller xử lý interaction
- Service xử lý nghiệp vụ

---

## 2. Naming Convention

- Classes: PascalCase
- Functions: snake_case
- Files: snake_case

---

## 3. Code Structure Rules

- UI không import services trực tiếp
- Controller gọi service
- Domain không import UI

---

## 4. Debug Strategy

- print state
- log command
- isolate bug nhỏ

---

## 5. Performance Tips

- Không block UI thread
- Dùng QThread cho task nặng
- Cache thumbnail

---

## 6. Common Mistakes

❌ Logic trong widget  
❌ Không dùng command pattern  
❌ Prompt quá lớn  

---

## 7. Refactor Strategy

- Refactor mỗi 3–5 feature
- Tách module khi file >300 dòng

---

## 8. AI Usage Tips

- Luôn chia nhỏ task
- Luôn yêu cầu explanation
- Luôn test sau mỗi bước

---

## 9. Final Advice

- Build chậm nhưng chắc
- Giữ app luôn chạy được
