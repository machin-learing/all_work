CREATE DATABASE IF NOT EXISTS text_rewrite_demo DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE text_rewrite_demo;

CREATE TABLE IF NOT EXISTS users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  username VARCHAR(50) NOT NULL UNIQUE,
  full_name VARCHAR(100) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  is_admin TINYINT(1) NOT NULL DEFAULT 0,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS role_options (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  code VARCHAR(50) NOT NULL UNIQUE,
  name VARCHAR(50) NOT NULL,
  description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_options (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  code VARCHAR(50) NOT NULL UNIQUE,
  name VARCHAR(50) NOT NULL,
  description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transfer_records (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  role_id BIGINT NOT NULL,
  model_id BIGINT NOT NULL,
  source_text TEXT NOT NULL,
  rewritten_text TEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'success',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_transfer_user FOREIGN KEY (user_id) REFERENCES users(id),
  CONSTRAINT fk_transfer_role FOREIGN KEY (role_id) REFERENCES role_options(id),
  CONSTRAINT fk_transfer_model FOREIGN KEY (model_id) REFERENCES model_options(id)
);

CREATE TABLE IF NOT EXISTS accepted_samples (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  transfer_id BIGINT NOT NULL,
  user_id BIGINT NOT NULL,
  role_code VARCHAR(50) NOT NULL,
  role_name VARCHAR(50) NOT NULL,
  model_code VARCHAR(50) NOT NULL,
  model_name VARCHAR(50) NOT NULL,
  source_text TEXT NOT NULL,
  rewritten_text TEXT NOT NULL,
  review_status VARCHAR(20) NOT NULL DEFAULT 'pending',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_accepted_transfer_user (transfer_id, user_id),
  CONSTRAINT fk_accepted_transfer FOREIGN KEY (transfer_id) REFERENCES transfer_records(id),
  CONSTRAINT fk_accepted_user FOREIGN KEY (user_id) REFERENCES users(id)
);

INSERT INTO role_options (code, name, description)
VALUES
  ('boss', '老板', '上级，远距离，工作领域'),
  ('colleague', '同事', '平级，中等距离，工作领域'),
  ('close_friend', '好朋友', '平等，近距离，生活领域'),
  ('girlfriend', '女朋友', '平等，最近距离，恋爱领域'),
  ('mother', '母亲', '晚辈→长辈，近距离，家庭领域')
ON DUPLICATE KEY UPDATE name = VALUES(name), description = VALUES(description);

INSERT INTO model_options (code, name, description)
VALUES
  ('deepseek_api', 'DeepSeek 教师模型', '千帆 DeepSeek V3.2，真实 API 调用'),
  ('transformer_scratch', '规则改写', '基于角色前后缀模板的规则 baseline'),
  ('lora_finetuned', 'LoRA 微调模型', 'mT0-large + LoRA 微调模型')
ON DUPLICATE KEY UPDATE name = VALUES(name), description = VALUES(description);

INSERT INTO users (username, full_name, password_hash, is_admin, is_active)
VALUES
  ('admin', '系统管理员', '$2b$12$NF8WWvaG.3qI3AM15.HNEO52h0UpSnjZN1fOu15R.FJNUGcDw/Soe', 1, 1)
ON DUPLICATE KEY UPDATE full_name = VALUES(full_name);
