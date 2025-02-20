import { Body, Controller, Post, HttpCode, HttpStatus } from '@nestjs/common';
import { AuthService } from './auth.service';

@Controller('auth')
export class AuthController {
  constructor(private authService: AuthService) {}

  @HttpCode(HttpStatus.OK)
  @Post('login')
  signIn(@Body() signInDto: Record<string, any>) {
    // TODO: Replace the DTO with a validator https://docs.nestjs.com/techniques/validation
    return this.authService.signIn(signInDto.username, signInDto.password);

    // TODO: Catch exceptions and throw the appropriate HTTP error
  }
}
