import { Injectable } from '@nestjs/common';

// This should be a real class/interface representing a user entity
export type User = any;

@Injectable()
export class UsersService {
  // TODO: Replace with a function that loads the JSON user file
  private readonly users = [
    {
      email: 'test@test.com',
      password: 'changeme',
    },
    {
      email: 'test1@test.com',
      password: 'guess',
    },
  ];

  async findOne(email: string): Promise<User | undefined> {
    // TODO: Also match password or throw an error if not found
    return this.users.find((user) => user.email === email);
  }
}
