from path_generate import *
import numpy as np
import math
import scipy.linalg as la
import matplotlib.pyplot as plt
import bisect
import datetime

import config

# 定义LQR 计算所需要的数据结构，以及DLQR的求解方法

dt = 0.1  # time tick[s]
L = 0.5  # Wheel base of the vehicle [m]
max_steer = np.deg2rad(45.0)  # maximum steering angle[rad]

Kp = 10.0  # speed proportional gain
Ki = 0.001
kd = 2.0

# LQR parameter
Q = np.eye(4)
R = np.eye(1)

show_animation = config.show_animation  # 是否画图，改这个即可

# State 对象表示自车的状态，位置x、y，以及横摆角yaw、速度v
class State:

    def __init__(self, x=0.0, y=0.0, yaw=0.0, v=0.0):
        self.x = x
        self.y = y
        self.yaw = yaw
        self.v = v

# 更新自车的状态，采样时间足够小，则认为这段时间内速度相同，加速度相同，使用匀速模型更新位置
def update(state, a, delta):

    if delta >= max_steer:
        delta = max_steer
    if delta <= - max_steer:
        delta = - max_steer

    state.x = state.x + state.v * math.cos(state.yaw) * dt
    state.y = state.y + state.v * math.sin(state.yaw) * dt
    state.yaw = state.yaw + state.v / L * math.tan(delta) * dt
    state.v = state.v + a * dt

    return state

def pi_2_pi(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi

# 实现离散Riccati equation 的求解方法
def solve_dare(A, B, Q, R):
    """
    solve a discrete time_Algebraic Riccati equation (DARE)
    """
    x = Q
    x_next = Q
    max_iter = 150
    eps = 0.01

    for i in range(max_iter):
        x_next = A.T @ x @ A - A.T @ x @ B @ \
                 la.inv(R + B.T @ x @ B) @ B.T @ x @ A + Q
        if (abs(x_next - x)).max() < eps:
            break
        x = x_next

    return x_next

# 返回值K 即为LQR 问题求解方法中系数K的解
def dlqr(A, B, Q, R):
    """Solve the discrete time lqr controller.
    x[k+1] = A x[k] + B u[k]
    cost = sum x[k].T*Q*x[k] + u[k].T*R*u[k]
    # ref Bertsekas, p.151
    """

    # first, try to solve the ricatti equation
    X = solve_dare(A, B, Q, R)

    # compute the LQR gain
    K = la.inv(B.T @ X @ B + R) @ (B.T @ X @ A)

    eig_result = la.eig(A - B @ K)

    return K, X, eig_result[0]

# 计算距离自车当前位置最近的参考点
def calc_nearest_index(state, cx, cy, cyaw):
    dx = [state.x - icx for icx in cx]
    dy = [state.y - icy for icy in cy]

    d = [idx ** 2 + idy ** 2 for (idx, idy) in zip(dx, dy)]

    mind = min(d)

    ind = d.index(mind)

    mind = math.sqrt(mind)

    dxl = cx[ind] - state.x
    dyl = cy[ind] - state.y

    angle = pi_2_pi(cyaw[ind] - math.atan2(dyl, dxl))
    if angle < 0:
        mind *= -1

    return ind, mind


class Spline:
    """
    Cubic Spline class
    """

    def __init__(self, x, y):
        self.b, self.c, self.d, self.w = [], [], [], []

        self.x = x
        self.y = y

        self.nx = len(x)  # dimension of x
        h = np.diff(x)

        # calc coefficient c
        self.a = [iy for iy in y]

        # calc coefficient c
        A = self.__calc_A(h)
        B = self.__calc_B(h)
        self.c = np.linalg.solve(A, B)
        #  print(self.c1)

        # calc spline coefficient b and d
        for i in range(self.nx - 1):
            self.d.append((self.c[i + 1] - self.c[i]) / (3.0 * h[i]))
            tb = (self.a[i + 1] - self.a[i]) / h[i] - h[i] * \
                (self.c[i + 1] + 2.0 * self.c[i]) / 3.0
            self.b.append(tb)

    def calc(self, t):
        """
        Calc position
        if t is outside of the input x, return None
        """

        if t < self.x[0]:
            return None
        elif t > self.x[-1]:
            return None

        i = self.__search_index(t)
        dx = t - self.x[i]
        result = self.a[i] + self.b[i] * dx + \
            self.c[i] * dx ** 2.0 + self.d[i] * dx ** 3.0

        return result

    def calcd(self, t):
        """
        Calc first derivative
        if t is outside of the input x, return None
        """

        if t < self.x[0]:
            return None
        elif t > self.x[-1]:
            return None

        i = self.__search_index(t)
        dx = t - self.x[i]
        result = self.b[i] + 2.0 * self.c[i] * dx + 3.0 * self.d[i] * dx ** 2.0
        return result

    def calcdd(self, t):
        """
        Calc second derivative
        """

        if t < self.x[0]:
            return None
        elif t > self.x[-1]:
            return None

        i = self.__search_index(t)
        dx = t - self.x[i]
        result = 2.0 * self.c[i] + 6.0 * self.d[i] * dx
        return result

    def __search_index(self, x):
        """
        search data segment index
        """
        return bisect.bisect(self.x, x) - 1

    def __calc_A(self, h):
        """
        calc matrix A for spline coefficient c
        """
        A = np.zeros((self.nx, self.nx))
        A[0, 0] = 1.0
        for i in range(self.nx - 1):
            if i != (self.nx - 2):
                A[i + 1, i + 1] = 2.0 * (h[i] + h[i + 1])
            A[i + 1, i] = h[i]
            A[i, i + 1] = h[i]

        A[0, 1] = 0.0
        A[self.nx - 1, self.nx - 2] = 0.0
        A[self.nx - 1, self.nx - 1] = 1.0
        #  print(A)
        return A

    def __calc_B(self, h):
        """
        calc matrix B for spline coefficient c
        """
        B = np.zeros(self.nx)
        for i in range(self.nx - 2):
            B[i + 1] = 3.0 * (self.a[i + 2] - self.a[i + 1]) / \
                h[i + 1] - 3.0 * (self.a[i + 1] - self.a[i]) / h[i]
        return B

class Spline2D:
    """
    2D Cubic Spline class
    """

    def __init__(self, x, y):
        self.s = self.__calc_s(x, y)
        self.sx = Spline(self.s, x)
        self.sy = Spline(self.s, y)

    def __calc_s(self, x, y):
        dx = np.diff(x)
        dy = np.diff(y)
        self.ds = [math.sqrt(idx ** 2 + idy ** 2)
                   for (idx, idy) in zip(dx, dy)]
        s = [0]
        s.extend(np.cumsum(self.ds))
        return s

    def calc_position(self, s):
        """
        calc position
        """
        x = self.sx.calc(s)
        y = self.sy.calc(s)

        return x, y

    def calc_curvature(self, s):
        """
        calc curvature
        """
        dx = self.sx.calcd(s)
        ddx = self.sx.calcdd(s)
        dy = self.sy.calcd(s)
        ddy = self.sy.calcdd(s)
        k = (ddy * dx - ddx * dy) / ((dx ** 2 + dy ** 2)**(3 / 2))
        return k

    def calc_yaw(self, s):
        """
        calc yaw
        """
        dx = self.sx.calcd(s)
        dy = self.sy.calcd(s)
        yaw = math.atan2(dy, dx)
        return yaw

def PIDControl(target, current):
    a = Kp * (target - current)
    return a

def lqr_steering_control(state, cx, cy, cyaw, ck, pe, pth_e):
    ind, e = calc_nearest_index(state, cx, cy, cyaw)

    k = ck[ind]
    v = state.v
    th_e = pi_2_pi(state.yaw - cyaw[ind])
    # e是自车到轨迹的距离
    # dot_e是自车到轨迹的距离的变化率
    # th_e是自车与期望轨迹的角度偏差
    # dot_th_e是自车与期望轨迹的角度偏差的变化率
    # delta_v是当前车速与期望车速的偏差

    A = np.zeros((4, 4))
    A[0, 0] = 1.0
    A[0, 1] = dt
    A[1, 2] = v
    A[2, 2] = 1.0
    A[2, 3] = dt
    # print(A)

    B = np.zeros((4, 1))
    B[3, 0] = v / L

    K, _, _ = dlqr(A, B, Q, R)

    x = np.zeros((4, 1))

    x[0, 0] = e
    x[1, 0] = (e - pe) / dt
    x[2, 0] = th_e
    x[3, 0] = (th_e - pth_e) / dt

    ff = math.atan2(L * k, 1)
    fb = pi_2_pi((-K @ x)[0, 0])

    delta = ff + fb

    return delta, ind, e, th_e

def calc_spline_course(x, y, ds=0.1):
    sp = Spline2D(x, y)
    s = list(np.arange(0, sp.s[-1], ds))

    rx, ry, ryaw, rk = [], [], [], []
    for i_s in s:
        ix, iy = sp.calc_position(i_s)
        rx.append(ix)
        ry.append(iy)
        ryaw.append(sp.calc_yaw(i_s))
        rk.append(sp.calc_curvature(i_s))

    return rx, ry, ryaw, rk, s

def calc_speed_profile(cx, cy, cyaw, target_speed):
    speed = [target_speed for i in range(len(cx))]
    speed[-1] = 0
    return speed

def closed_loop_prediction(cx, cy, cyaw, ck, speed_profile, goal):
    T = 500.0  # max simulation time
    goal_dis = 0.3
    stop_speed = 0.00

    state = State(x=-0.0, y=-0.0, yaw=0.0, v=0.0)

    time = 0.0
    x = [state.x]
    y = [state.y]
    yaw = [state.yaw]
    v = [state.v]
    t = [0.0]

    e, e_th = 0.0, 0.0

    while T >= time:
        dl, target_ind, e, e_th = lqr_steering_control(
            state, cx, cy, cyaw, ck, e, e_th)
        ai = PIDControl(speed_profile[target_ind], state.v)
        state = update(state, ai, dl)
        if abs(state.v) <= stop_speed:
            target_ind += 1
        time = time + dt

    # check goal
        dx = state.x - goal[0]
        dy = state.y - goal[1]
        #print(state.x, goal[0], state.y, goal[1])
        if math.hypot(dx, dy) <= goal_dis:
            #print("Goal reached!")
            break

        x.append(state.x)
        y.append(state.y)
        yaw.append(state.yaw)
        v.append(state.v)
        t.append(time)

    return t, x, y, yaw, v

def closed_loop_prediction_realtime(cx, cy, cyaw, ck, speed_profile, goal):
    T = 500.0  # max simulation time
    goal_dis = 0.3
    stop_speed = 0.00

    state = State(x=-0.0, y=-0.0, yaw=0.0, v=0.0)

    time = 0.0
    x = [state.x]
    y = [state.y]
    yaw = [state.yaw]
    v = [state.v]
    t = [0.0]

    e, e_th = 0.0, 0.0

    while T >= time:
        dl, target_ind, e, e_th = lqr_steering_control(
            state, cx, cy, cyaw, ck, e, e_th)
        ai = PIDControl(speed_profile[target_ind], state.v)
        state = update(state, ai, dl)
        if abs(state.v) <= stop_speed:
            target_ind += 1
        time = time + dt

    # check goal
        dx = state.x - goal[0]
        dy = state.y - goal[1]
        #print(state.x, goal[0], state.y, goal[1])
        if math.hypot(dx, dy) <= goal_dis:
            print("Goal reached!")
            break

        x.append(state.x)
        y.append(state.y)
        yaw.append(state.yaw)
        v.append(state.v)
        t.append(time)

    return t, x, y, yaw, v

def competitionItem(itemNum, ax=[], ay=[]):
    if itemNum == 4:
        # print(ax, ay)
        ax.append(-1.891)
        ay.append(-51.341)

    else:
        # 必须要经过的途径点
        ax = [0.0, 6.0, 12.5, 10.0, 17.5, 20.0, 25.0, 35.0]
        ay = [0.0, -3.0, -5.0, 6.5, 3.0, 0.0, 0.0, -1.0]
        # ax = [0.0, 6.0]
        # ay = [0.0, -3.0]

    goal = [ax[-1], ay[-1]]

    return ax, ay, goal

def lqrControl(itemNum, ax=[], ay=[]):
    # print("LQR steering control tracking start!!")

    ax, ay, goal = competitionItem(itemNum, ax, ay)

    # 使用三次样条插值方法，根据途经点生成轨迹，x、y、yaw、曲率k，距离s
    cx, cy, cyaw, ck, s = calc_spline_course(ax, ay, ds=0.1)

    # print(cyaw)

    target_speed = 10.0 / 3.6  # simulation parameter km/h -> m/s
    sp = calc_speed_profile(cx, cy, cyaw, target_speed)
    t, x, y, yaw, v = closed_loop_prediction(cx, cy, cyaw, ck, sp, goal)
    # print(len(v))

    if show_animation:  # pragma: no cover
        plt.close()
        plt.subplots(1)
        plt.plot(ax, ay, "xb", label="input")
        plt.plot(cx, cy, "-r", label="spline")
        plt.plot(x, y, "-g", label="tracking")
        plt.plot(t, v, "-y")
        plt.plot(t, yaw, "#a04398")
        plt.grid(True)
        plt.axis("equal")
        plt.xlabel("x[m]")
        plt.ylabel("y[m]")
        plt.legend()
        plt.show()

    return x, y, yaw, v

def lqrControl_realtime(itemNum, ax=[], ay=[]):
    print("LQR steering control tracking start!!")

    ax, ay, goal = competitionItem(itemNum, ax, ay)

    # 使用三次样条插值方法，根据途经点生成轨迹，x、y、yaw、曲率k，距离s
    cx, cy, cyaw, ck, s = calc_spline_course(ax, ay, ds=0.1)

    # print(cyaw)

    target_speed = 10.0 / 3.6  # simulation parameter km/h -> m/s
    sp = calc_speed_profile(cx, cy, cyaw, target_speed)
    t, x, y, yaw, v = closed_loop_prediction(cx, cy, cyaw, ck, sp, goal)
    # print(len(v))

    if show_animation:  # pragma: no cover
        plt.close()
        plt.subplots(1)
        plt.plot(ax, ay, "xb", label="input")
        plt.plot(cx, cy, "-r", label="spline")
        plt.plot(x, y, "-g", label="tracking")
        plt.plot(t, v, "-y")
        plt.plot(t, yaw, "#a04398")
        plt.grid(True)
        plt.axis("equal")
        plt.xlabel("x[m]")
        plt.ylabel("y[m]")
        plt.legend()
        plt.show()

    return x, y, yaw, v

if __name__ == "__main__":
    lqrControl(1)