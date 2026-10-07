/**
 * 业务错误 code → 前端文案（模板为中文优先）。
 *
 * 后端 `DomainError.code` 是稳定标识（见 backend/app/services/errors.py 与
 * backend/app/api/error_handlers.py）；未知 code 时回落到后端 detail。
 * 新项目的业务 code 映射在此追加。
 */
export const ERROR_MESSAGES: Record<string, string> = {
  invalid_credentials: "账号或密码错误",
  account_disabled: "账号已被禁用，请联系管理员",
  password_required_change: "请先修改初始密码",
  old_password_incorrect: "旧密码错误",
  password_unchanged: "新密码不能与旧密码相同",
  forbidden: "无权访问该资源",
  not_found: "资源不存在或已被删除",
  username_taken: "该账号已存在",
  teacher_not_found: "指定的指导教师不存在或已禁用",
  admin_immutable: "管理员账号不可操作",
  invalid_fields: "提交了不允许修改的字段",
  invalid_action: "当前操作不被允许",
  unsupported_file_type: "仅支持 .docx 文件",
  empty_file: "请选择文件",
  file_too_large: "文件超过 50MB 限制",
  internal_error: "服务器开小差了，请稍后重试",
};

/** 查 code 对应文案；未登记时返回 undefined（由调用方回落 detail）。 */
export function messageForCode(code: string | undefined): string | undefined {
  if (!code) {
    return undefined;
  }
  return ERROR_MESSAGES[code];
}
