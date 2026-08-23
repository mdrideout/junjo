import { describe, it, expect } from 'vitest'
import { api, generateMock } from '../../auth/test-utils/openapi-mock-generator'
import { UserResponseSchema } from '../../auth/response-schemas'
import { ApiKeyCreateResponseSchema } from '../../features/api-keys/response-schemas'
import { FlushWALResponseSchema } from '../../features/settings/schemas'

describe('API Contract: Mutation Operations Response Schemas', () => {
  describe('Authentication', () => {
    it('UserResponse schema matches create-first-user endpoint', () => {
      const { mock } = generateMock('create_first_user_users_create_first_user_post')
      const result = UserResponseSchema.parse(mock)

      expect(result.message).toBeDefined()
      expect(typeof result.message).toBe('string')
      expect(result.message.length).toBeGreaterThan(0)
    })

    it('UserResponse schema matches sign-in endpoint', () => {
      const { mock } = generateMock('sign_in_sign_in_post')
      const result = UserResponseSchema.parse(mock)

      expect(result.message).toBeDefined()
      expect(typeof result.message).toBe('string')
    })

    it('UserResponse schema matches sign-out endpoint', () => {
      const { mock } = generateMock('sign_out_sign_out_post')
      const result = UserResponseSchema.parse(mock)

      expect(result.message).toBeDefined()
      expect(typeof result.message).toBe('string')
    })
  })

  describe('User Management', () => {
    it('UserResponse schema matches create user endpoint', () => {
      const { mock } = generateMock('create_user_users_post')
      const result = UserResponseSchema.parse(mock)

      expect(result.message).toBeDefined()
      expect(typeof result.message).toBe('string')
    })

    it('UserResponse schema matches delete user endpoint', () => {
      const { mock } = generateMock('delete_user_users__user_id__delete')
      const result = UserResponseSchema.parse(mock)

      expect(result.message).toBeDefined()
      expect(typeof result.message).toBe('string')
    })
  })

  describe('API Keys', () => {
    it('ApiKeyCreateResponse schema matches create API key endpoint', () => {
      const { mock } = generateMock('create_api_key_api_keys_post')
      const result = ApiKeyCreateResponseSchema.parse(mock)

      // Validate structure
      expect(result.id).toBeDefined()
      expect(typeof result.id).toBe('string')

      // Validate the secret key is present (only shown on creation)
      expect(result.key).toBeDefined()
      expect(typeof result.key).toBe('string')
      expect(result.key.length).toBeGreaterThan(0)

      expect(result.name).toBeDefined()
      expect(typeof result.name).toBe('string')

      expect(result.created_at).toBeDefined()
      expect(typeof result.created_at).toBe('string')
    })
  })

  describe('Admin Operations', () => {
    it('FlushWALResponse schema matches flush-wal endpoint', () => {
      const { mock } = generateMock('flush_wal_api_admin_flush_wal_post')
      const result = FlushWALResponseSchema.parse(mock)

      expect(result.success).toBeDefined()
      expect(typeof result.success).toBe('boolean')
      expect(result.message).toBeDefined()
      expect(typeof result.message).toBe('string')
    })
  })

  describe('Path Parameter Types', () => {
    it('DELETE /users/{user_id} parameter is defined as string', () => {
      const operation = api.getOperation('delete_user_users__user_id__delete')
      const userIdParam = operation?.parameters?.find((p) => 'name' in p && p.name === 'user_id')

      expect(userIdParam).toBeDefined()
      const schema = userIdParam && 'schema' in userIdParam ? userIdParam.schema : undefined
      expect(schema && typeof schema === 'object' && 'type' in schema ? schema.type : undefined).toBe(
        'string',
      )
    })

    it('DELETE /api_keys/{id} parameter is defined as string', () => {
      const operation = api.getOperation('delete_api_key_api_keys__id__delete')
      const idParam = operation?.parameters?.find((p) => 'name' in p && p.name === 'id')

      expect(idParam).toBeDefined()
      const schema = idParam && 'schema' in idParam ? idParam.schema : undefined
      expect(schema && typeof schema === 'object' && 'type' in schema ? schema.type : undefined).toBe(
        'string',
      )
    })

  })
})
