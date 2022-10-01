#include "math_function.h"

typedef unsigned char uchar;

using namespace std;

template<typename T1,typename T2>
bool is_key_color(T1* pixel,const vector<vector<T2>> &colors, const double DISTANCE, const int CHANNEL){
    double min_dis = 1e9;
	for(auto color:colors)
		min_dis=min(min_dis, calc_distance(pixel, color, CHANNEL));
	return min_dis < DISTANCE;
}

template<typename T1,typename T2>
bool is_key_color(const vector<T1> &pixel,const vector<vector<T2>> &colors, const double DISTANCE, const int CHANNEL){
    return is_key_color(&pixel[0], colors, DISTANCE, CHANNEL);
}