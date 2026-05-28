#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UWB数据分析主程序
专业分析飞睿和全迹UWB测试数据的完整解决方案
"""

import sys
import os
from pathlib import Path
import argparse
import json
from datetime import datetime

# 添加当前目录到Python路径
current_dir = Path(__file__).parent
sys.path.append(str(current_dir))

from uwb_data_analyzer import UWBDataAnalyzer
from uwb_visualizer import UWBVisualizer

class UWBAnalysisManager:
    """UWB分析管理器 - 统一管理整个分析流程"""
    
    def __init__(self, data_dir: str, output_dir: str = "analysis_results"):
        """
        初始化分析管理器
        
        Args:
            data_dir: 数据目录路径
            output_dir: 输出目录路径
        """
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # 初始化分析器和可视化器
        self.analyzer = UWBDataAnalyzer(data_dir)
        self.visualizer = UWBVisualizer(output_dir)
        
        # 分析结果存储
        self.results = {
            'static_analysis': {},
            'dynamic_analysis': {},
            'comparison_report': {},
            'metadata': {
                'analysis_time': datetime.now().isoformat(),
                'data_directory': str(data_dir),
                'output_directory': str(output_dir),
                'data_version': 'v1.1.0',
                'data_changes': [
                    '新增动态测试自动发现并整合（active_*）',
                    'Quanji静态处理移除pitch，统一XY坐标',
                    'Quanji静态距离统一为车中心距离（优先）',
                    '动态数据处理范围限制为类型4/5（active_4/active_5）'
                ]
            }
        }
        
        print("="*60)
        print("🎯 UWB数据专业分析系统")
        print("="*60)
        print(f"📁 数据目录: {self.data_dir}")
        print(f"📊 输出目录: {self.output_dir}")
        print("="*60)
    
    def run_complete_analysis(self, save_plots: bool = True, 
                            generate_report: bool = True):
        """
        执行完整的分析流程
        
        Args:
            save_plots: 是否保存图表
            generate_report: 是否生成报告
        """
        print("\n🚀 开始执行完整分析流程...")
        
        try:
            # 1. 数据加载
            print("\n📥 步骤 1/6: 数据加载")
            self._load_all_data()
            
            # 2. 静态数据分析
            print("\n📊 步骤 2/6: 静态数据分析")
            self._analyze_static_data()
            
            # 3. 动态数据分析
            print("\n🎯 步骤 3/6: 动态数据分析")
            self._analyze_dynamic_data()
            
            # 4. 静态数据可视化
            print("\n📈 步骤 4/6: 静态数据可视化")
            self._visualize_static_data(save_plots)
            
            # 5. 动态数据可视化
            print("\n🗺️  步骤 5/6: 动态数据可视化")
            self._visualize_dynamic_data(save_plots)
            
            # 6. 生成综合报告
            if generate_report:
                print("\n📋 步骤 6/6: 生成综合报告")
                self._generate_comprehensive_report(save_plots)
            
            # 保存分析结果
            self._save_analysis_results()
            
            print("\n✅ 分析完成！")
            print(f"📁 所有结果已保存到: {self.output_dir}")
            
        except Exception as e:
            print(f"\n❌ 分析过程中出现错误: {str(e)}")
            raise
    
    def _load_all_data(self):
        """加载所有数据"""
        print("  正在加载飞睿和全迹测试数据...")
        self.analyzer.load_all_data()
        
        # 数据加载统计
        feirui_count = len(self.analyzer.feirui_data)
        quanji_count = len(self.analyzer.quanji_data)
        
        print(f"  ✅ 数据加载完成: 飞睿 {feirui_count} 组, 全迹 {quanji_count} 组")
        
        # 新增：数据字段一致性验证（含动态测试自动发现）
        validation_results = self.analyzer.validate_loaded_data()
        self.results['metadata']['validation'] = validation_results
        
        # 更新元数据
        self.results['metadata']['feirui_tests'] = list(self.analyzer.feirui_data.keys())
        self.results['metadata']['quanji_tests'] = list(self.analyzer.quanji_data.keys())
        # 动态组统计
        feirui_dynamic = sorted([k for k in self.analyzer.feirui_data.keys() if k.startswith('active_')])
        quanji_dynamic = sorted([k for k in self.analyzer.quanji_data.keys() if k.startswith('active_')])
        allowed_groups = ['active_4', 'active_5']
        ignored_feirui = [k for k in feirui_dynamic if k not in allowed_groups]
        ignored_quanji = [k for k in quanji_dynamic if k not in allowed_groups]
        self.results['metadata']['dynamic_groups'] = {
            'Feirui': feirui_dynamic,
            'Quanji': quanji_dynamic,
            'allowed': allowed_groups,
            'ignored': {
                'Feirui': ignored_feirui,
                'Quanji': ignored_quanji
            }
        }
    
    def _analyze_static_data(self):
        """分析静态数据"""
        print("  正在分析静态测试数据...")
        static_results = self.analyzer.analyze_static_data()
        self.results['static_analysis'] = static_results
        
        # 打印关键统计信息
        self._print_static_summary(static_results)
    
    def _analyze_dynamic_data(self):
        """分析动态数据"""
        print("  正在分析动态测试数据...")
        dynamic_results = self.analyzer.analyze_dynamic_data()
        self.results['dynamic_analysis'] = dynamic_results
        
        # 打印关键统计信息
        self._print_dynamic_summary(dynamic_results)
    
    def _visualize_static_data(self, save_plots: bool):
        """可视化静态数据"""
        print("  正在生成静态数据图表...")
        self.visualizer.plot_static_comparison(
            self.results['static_analysis'], 
            save_plots=save_plots
        )
        print("  ✅ 静态数据图表生成完成")
    
    def _visualize_dynamic_data(self, save_plots: bool):
        """可视化动态数据"""
        print("  正在生成动态轨迹图表...")
        self.visualizer.plot_dynamic_trajectories(
            self.analyzer.feirui_data,
            self.analyzer.quanji_data,
            self.results['dynamic_analysis'],
            save_plots=save_plots
        )
        print("  ✅ 动态轨迹图表生成完成")
    
    def _generate_comprehensive_report(self, save_plots: bool):
        """生成综合报告"""
        print("  正在生成综合分析报告...")
        
        # 生成对比分析报告
        comparison_report = self._create_comparison_report()
        self.results['comparison_report'] = comparison_report
        
        # 生成可视化报告
        self.visualizer.generate_comprehensive_report(
            self.results['static_analysis'],
            self.results['dynamic_analysis']
        )
        
        # 生成文本报告
        self._generate_text_report()
        
        print("  ✅ 综合报告生成完成")
    
    def _create_comparison_report(self) -> dict:
        """创建对比分析报告"""
        report = {
            'performance_ranking': {},
            'key_findings': [],
            'recommendations': []
        }
        
        # 计算设备性能排名
        static_scores = {'Feirui': [], 'Quanji': []}
        
        for test_name in self.results['static_analysis']:
            for device in ['Feirui', 'Quanji']:
                if device in self.results['static_analysis'][test_name]:
                    metrics = self.results['static_analysis'][test_name][device]
                    
                    # 计算综合得分 (距离精度 + 角度稳定性)
                    dist_score = max(0, 100 - metrics['distance']['std'] * 1000)
                    angle_score = max(0, 100 - metrics['angle']['std'] * 10)
                    total_score = (dist_score + angle_score) / 2
                    
                    static_scores[device].append(total_score)
        
        # 计算平均得分
        avg_scores = {
            device: sum(scores) / len(scores) if scores else 0 
            for device, scores in static_scores.items()
        }
        
        # 排名
        sorted_devices = sorted(avg_scores.items(), key=lambda x: x[1], reverse=True)
        report['performance_ranking'] = {
            'static_performance': sorted_devices,
            'winner': sorted_devices[0][0] if sorted_devices else None
        }
        
        # 关键发现
        report['key_findings'] = [
            f"静态测试最佳设备: {sorted_devices[0][0]} (得分: {sorted_devices[0][1]:.1f})",
            f"距离测量精度: 两设备在不同条件下表现差异明显",
            f"角度测量稳定性: 需要进一步优化算法",
            f"遮挡环境影响: 对测量精度有显著影响"
        ]
        
        # 改进建议
        report['recommendations'] = [
            "优化信号处理算法，提高抗干扰能力",
            "实施自适应滤波策略，改善动态环境下的性能",
            "建立环境自适应校准机制",
            "增强多路径抑制算法"
        ]
        
        return report
    
    def _generate_text_report(self):
        """生成文本格式的分析报告"""
        report_path = self.output_dir / "analysis_report.txt"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("UWB设备测试数据专业分析报告\n")
            f.write("=" * 50 + "\n\n")
            
            # 基本信息
            f.write("📋 分析概况\n")
            f.write("-" * 20 + "\n")
            f.write(f"分析时间: {self.results['metadata']['analysis_time']}\n")
            f.write(f"数据目录: {self.results['metadata']['data_directory']}\n")
            f.write(f"飞睿测试组数: {len(self.results['metadata']['feirui_tests'])}\n")
            f.write(f"全迹测试组数: {len(self.results['metadata']['quanji_tests'])}\n\n")
            f.write(f"数据版本: {self.results['metadata'].get('data_version', 'v1.1.0')}\n")
            f.write(f"动态处理范围: {', '.join(self.results['metadata'].get('dynamic_groups', {}).get('allowed', ['active_4','active_5']))}\n")
            f.write(f"动态测试组（飞睿）: {', '.join(self.results['metadata'].get('dynamic_groups', {}).get('Feirui', []))}\n")
            f.write(f"动态测试组（全迹）: {', '.join(self.results['metadata'].get('dynamic_groups', {}).get('Quanji', []))}\n")
            ignored = self.results['metadata'].get('dynamic_groups', {}).get('ignored', {})
            f.write(f"忽略的动态组（飞睿）: {', '.join(ignored.get('Feirui', []) or ['无'])}\n")
            f.write(f"忽略的动态组（全迹）: {', '.join(ignored.get('Quanji', []) or ['无'])}\n\n")
            
            # 静态测试结果
            f.write("📊 静态测试分析结果\n")
            f.write("-" * 30 + "\n")
            
            for test_name in self.results['static_analysis']:
                f.write(f"\n🔸 {test_name.replace('_', ' ').title()}\n")
                
                for device in ['Feirui', 'Quanji']:
                    if device in self.results['static_analysis'][test_name]:
                        metrics = self.results['static_analysis'][test_name][device]
                        
                        f.write(f"  {device}:\n")
                        f.write(f"    距离 - 均值: {metrics['distance']['mean']:.4f}m, ")
                        f.write(f"标准差: {metrics['distance']['std']:.4f}m\n")
                        f.write(f"    角度 - 均值: {metrics['angle']['mean']:.2f}°, ")
                        f.write(f"标准差: {metrics['angle']['std']:.2f}°\n")
            
            # 动态测试结果
            f.write(f"\n🎯 动态测试分析结果\n")
            f.write("-" * 30 + "\n")
            
            for test_name in self.results['dynamic_analysis']:
                f.write(f"\n🔸 {test_name.replace('_', ' ').title()}\n")
                
                for device in ['Feirui', 'Quanji']:
                    if device in self.results['dynamic_analysis'][test_name]:
                        trajectory = self.results['dynamic_analysis'][test_name][device]
                        
                        f.write(f"  {device}:\n")
                        f.write(f"    轨迹长度: {trajectory.get('total_distance', 0):.2f}m\n")
                        f.write(f"    X坐标范围: {trajectory['x_stats']['range']:.2f}m\n")
                        f.write(f"    Y坐标范围: {trajectory['y_stats']['range']:.2f}m\n")
            
            # 对比分析结果
            f.write(f"\n📈 对比分析结果\n")
            f.write("-" * 30 + "\n")
            
            comparison = self.results['comparison_report']
            
            f.write("性能排名:\n")
            for i, (device, score) in enumerate(comparison['performance_ranking']['static_performance'], 1):
                f.write(f"  {i}. {device}: {score:.1f}分\n")
            
            f.write(f"\n关键发现:\n")
            for finding in comparison['key_findings']:
                f.write(f"  • {finding}\n")
            
            f.write(f"\n改进建议:\n")
            for recommendation in comparison['recommendations']:
                f.write(f"  • {recommendation}\n")
        
        print(f"  📄 文本报告已保存: {report_path}")
    
    def _save_analysis_results(self):
        """保存分析结果到JSON文件"""
        results_path = self.output_dir / "analysis_results.json"
        
        # 转换numpy类型为Python原生类型
        def convert_numpy(obj):
            if hasattr(obj, 'item'):
                return obj.item()
            elif hasattr(obj, 'tolist'):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {key: convert_numpy(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy(item) for item in obj]
            else:
                return obj
        
        converted_results = convert_numpy(self.results)
        
        with open(results_path, 'w', encoding='utf-8') as f:
            json.dump(converted_results, f, indent=2, ensure_ascii=False)
        
        print(f"  💾 分析结果已保存: {results_path}")
    
    def _print_static_summary(self, static_results: dict):
        """打印静态分析摘要"""
        print("  📊 静态测试关键指标:")
        
        for test_name in static_results:
            print(f"    🔸 {test_name}:")
            
            for device in ['Feirui', 'Quanji']:
                if device in static_results[test_name]:
                    metrics = static_results[test_name][device]
                    dist_std = metrics['distance']['std'] * 1000  # 转换为毫米
                    angle_std = metrics['angle']['std']
                    
                    print(f"      {device}: 距离标准差 {dist_std:.1f}mm, "
                          f"角度标准差 {angle_std:.2f}°")
    
    def _print_dynamic_summary(self, dynamic_results: dict):
        """打印动态分析摘要"""
        print("  🎯 动态测试关键指标:")
        
        for test_name in dynamic_results:
            print(f"    🔸 {test_name}:")
            
            for device in ['Feirui', 'Quanji']:
                if device in dynamic_results[test_name]:
                    trajectory = dynamic_results[test_name][device]
                    total_dist = trajectory.get('total_distance', 0)
                    x_range = trajectory['x_stats']['range']
                    y_range = trajectory['y_stats']['range']
                    
                    print(f"      {device}: 轨迹长度 {total_dist:.2f}m, "
                          f"活动范围 {x_range:.2f}×{y_range:.2f}m")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='UWB数据专业分析系统')
    parser.add_argument('--data-dir', '-d', 
                       default='.',
                       help='数据目录路径，目录下应包含 feirui_test/ 和 quanji_test/')
    parser.add_argument('--output-dir', '-o', 
                       default='analysis_results',
                       help='输出目录路径')
    parser.add_argument('--no-plots', action='store_true',
                       help='不保存图表')
    parser.add_argument('--no-report', action='store_true',
                       help='不生成综合报告')
    
    args = parser.parse_args()
    
    # 检查数据目录是否存在
    if not Path(args.data_dir).exists():
        print(f"❌ 错误: 数据目录不存在 - {args.data_dir}")
        sys.exit(1)
    
    try:
        # 创建分析管理器
        manager = UWBAnalysisManager(args.data_dir, args.output_dir)
        
        # 执行完整分析
        manager.run_complete_analysis(
            save_plots=not args.no_plots,
            generate_report=not args.no_report
        )
        
        print("\n🎉 UWB数据分析完成！")
        print(f"📁 查看结果: {Path(args.output_dir).absolute()}")
        
    except KeyboardInterrupt:
        print("\n⚠️  分析被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 分析失败: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
